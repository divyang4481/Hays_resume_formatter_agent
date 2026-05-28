from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, StateGraph

from src.worker.agents.template_analysis.extractors.openxml_visual_extractor import extract_openxml_visual_evidence
from src.worker.agents.template_analysis.extractors.python_docx_visual_extractor import extract_python_docx_visual_evidence
from src.worker.agents.template_analysis.extractors.docling_visual_extractor import extract_docling_visual_evidence
from src.worker.agents.template_analysis.visual_reconciler import reconcile_visual_evidence
from src.worker.agents.template_analysis.table_role_classifier import classify_tables
from src.worker.agents.template_analysis.region_builder import build_visual_regions
from src.worker.agents.template_analysis.visual_field_candidate_builder import build_visual_field_candidates
from src.worker.agents.template_analysis.visual_debug import build_visual_debug_report
import os
from pathlib import Path
from src.shared.config import settings


from src.shared.models import GraphResult, JobStatus
from src.shared.storage import object_store
from src.worker.agents.template_analysis.extractors import (
    extract_docling_layout_evidence,
    extract_openxml_evidence,
    extract_python_docx_evidence,
    extract_visual_layout_evidence,
    reconcile_template_evidence,
)
from src.worker.agents.template_analysis.field_candidate_builder import (
    build_field_candidates_from_evidence,
)
from src.worker.agents.template_analysis.manifest_critic import critique_manifest
from src.worker.agents.template_analysis.logical_field_grouper import group_logical_fields_from_candidates
from src.worker.agents.template_analysis.manifest_validator import (
    validate_manifest_fields_against_layout,
)


logger = logging.getLogger(__name__)
TEMPLATE_ANALYSIS_PIPELINE_VERSION = "layout_v2_agentic_qc_2026_05_28"
PIPELINE_VERSION = TEMPLATE_ANALYSIS_PIPELINE_VERSION


class TemplateAnalysisState(TypedDict):
    template_id: str
    template_name: str
    template_object_key: str
    template_bytes: bytes
    evidence: dict[str, Any]
    visual_model: Any
    visual_regions: list
    use_visual_pipeline: bool
    layout: dict[str, Any]
    field_candidates: list[dict[str, Any]]
    fields: list[dict[str, Any]]
    grouped_fields: list[dict[str, Any]]
    critic: dict[str, Any]



def _extract_visual_evidence(state: TemplateAnalysisState) -> TemplateAnalysisState:
    tb = state["template_bytes"]
    filename = state.get("template_name") or "template.docx"
    ox = extract_openxml_visual_evidence(tb)
    pd = extract_python_docx_visual_evidence(tb)
    dl = extract_docling_visual_evidence(tb, filename)
    state["visual_model"] = reconcile_visual_evidence(ox, pd, dl)
    return state

def _build_visual_regions(state: TemplateAnalysisState) -> TemplateAnalysisState:
    model = state["visual_model"]
    classify_tables(model)
    regions = build_visual_regions(model)
    state["visual_regions"] = regions
    return state

def _build_visual_candidates(state: TemplateAnalysisState) -> TemplateAnalysisState:
    model = state["visual_model"]
    candidates = build_visual_field_candidates(model)
    state["field_candidates"] = candidates
    return state

def _check_pipeline(state: TemplateAnalysisState) -> str:
    # Read feature flag
    pipeline_mode = os.environ.get("TEMPLATE_ANALYSIS_PIPELINE", "visual_v1")
    state["use_visual_pipeline"] = pipeline_mode == "visual_v1"

    if state["use_visual_pipeline"]:
        return "visual"
    return "legacy"

def _load_template_bytes(state: TemplateAnalysisState) -> TemplateAnalysisState:
    if state.get("template_bytes"):
        return state
    state["template_bytes"] = object_store.get_bytes(state["template_object_key"])
    return state


def _extract_evidence(state: TemplateAnalysisState) -> TemplateAnalysisState:
    logger.info("[TemplateAnalysis] pipeline_version=%s", PIPELINE_VERSION)
    logger.info(
        "[TemplateAnalysis] graph_file=src/worker/agents/template_analysis/graph.py"
    )
    tb = state["template_bytes"]
    ox = extract_openxml_evidence(tb)
    pd = extract_python_docx_evidence(tb)
    dl = extract_docling_layout_evidence(
        tb, state.get("template_name") or "template.docx"
    )
    vl = extract_visual_layout_evidence(tb)
    state["layout"] = reconcile_template_evidence(ox, pd, dl, vl)
    state["evidence"] = {"openxml": ox, "python_docx": pd, "docling": dl, "visual": vl}
    return state


def _build_candidates(state: TemplateAnalysisState) -> TemplateAnalysisState:
    state["field_candidates"] = build_field_candidates_from_evidence(state["layout"])
    return state




def _group_validate_and_critic(state: TemplateAnalysisState) -> TemplateAnalysisState:
    raw = state.get("field_candidates", [])
    grouped = group_logical_fields_from_candidates(raw, state.get("layout", {}))

    pipeline_mode = os.environ.get("TEMPLATE_ANALYSIS_PIPELINE", "visual_v1")
    use_visual = pipeline_mode == "visual_v1"

    if use_visual:
        validated = grouped # Bypass block validation since it's built from visual regions directly
    else:
        validated = validate_manifest_fields_against_layout(
            grouped, {"blocks": state.get("layout", {}).get("canonical_blocks", [])}
        )


    critic = critique_manifest({"fields": validated, "layout": state.get("layout", {})})

    duplicate_count = len(validated) - len({f.get("name") for f in validated})
    repeat_groups_count = len([f for f in validated if f.get("field_type") == "array_object"])
    logger.info("[TemplateAnalysis] raw_candidates_count=%s", len(raw))
    logger.info("[TemplateAnalysis] grouped_fields_count=%s", len(grouped))
    logger.info("[TemplateAnalysis] duplicate_field_names=%s", max(0, duplicate_count))
    logger.info("[TemplateAnalysis] repeat_groups_count=%s", repeat_groups_count)
    logger.info("[TemplateAnalysis] critic_score=%s", critic.get("score"))
    state["grouped_fields"] = grouped
    state["fields"] = validated
    state["critic"] = critic
    return state



def build_template_analysis_graph():
    graph = StateGraph(TemplateAnalysisState)
    graph.add_node("load_template_bytes", _load_template_bytes)

    # Legacy path
    graph.add_node("extract_evidence", _extract_evidence)
    graph.add_node("build_candidates", _build_candidates)

    # Visual path
    graph.add_node("extract_visual_evidence", _extract_visual_evidence)
    graph.add_node("build_visual_regions", _build_visual_regions)
    graph.add_node("build_visual_candidates", _build_visual_candidates)

    graph.add_node("group_validate_and_critic", _group_validate_and_critic)

    graph.set_entry_point("load_template_bytes")

    # Conditional routing
    graph.add_conditional_edges(
        "load_template_bytes",
        _check_pipeline,
        {
            "visual": "extract_visual_evidence",
            "legacy": "extract_evidence"
        }
    )

    graph.add_edge("extract_evidence", "build_candidates")
    graph.add_edge("build_candidates", "group_validate_and_critic")

    graph.add_edge("extract_visual_evidence", "build_visual_regions")
    graph.add_edge("build_visual_regions", "build_visual_candidates")
    graph.add_edge("build_visual_candidates", "group_validate_and_critic")

    graph.add_edge("group_validate_and_critic", END)
    return graph.compile()
def run_template_analysis(
    template_id: str, template_name: str, template_object_key: str, template_bytes: bytes | None = None
) -> GraphResult:
    print(f"[TemplateAnalysis] pipeline_version={TEMPLATE_ANALYSIS_PIPELINE_VERSION}")
    print(f"[TemplateAnalysis] graph_module={__file__}")

    app = build_template_analysis_graph()
    result = app.invoke(
        {
            "template_id": template_id,
            "template_name": template_name,
            "template_object_key": template_object_key,
            "template_bytes": template_bytes or b"",
            "evidence": {},
            "layout": {},
            "field_candidates": [],
            "fields": [],
            "grouped_fields": [],
            "critic": {},
        }
    )
    manifest = {
        "manifest_id": str(uuid4()),
        "template_id": template_id,
        "version": 2,
        "manifest_schema": "template_manifest_v2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "layout": {
            "blocks_count": len(result.get("layout", {}).get("canonical_blocks", [])),
            "repeat_groups_count": len(
                result.get("layout", {}).get("repeat_groups", [])
            ),
        },
        "fields": result.get("fields", []),
    }

    from src.shared.config import settings

    if settings.app_env != "production":
        manifest["debug"] = {
            "pipeline_version": TEMPLATE_ANALYSIS_PIPELINE_VERSION,
            "graph_module": __file__,
            "blocks_count": len(result.get("layout", {}).get("canonical_blocks", [])),
            "fields_count": len(result.get("fields", [])),
            "raw_candidates_count": len(result.get("field_candidates", [])),
            "grouped_fields_count": len(result.get("grouped_fields", [])),
            "critic": result.get("critic", {}),
        }

    print(f"[TemplateAnalysis] manifest_version={manifest['version']}")
    print(f"[TemplateAnalysis] manifest_schema={manifest.get('manifest_schema')}")
    print(
        f"[TemplateAnalysis] blocks_count={len(result.get('layout', {}).get('canonical_blocks', []))}"
    )
    print(f"[TemplateAnalysis] fields_count={len(result.get('fields', []))}")


    if settings.app_env != "production" and os.environ.get("TEMPLATE_ANALYSIS_PIPELINE", "visual_v1") == "visual_v1":
        visual_model = result.get("visual_model")
        if visual_model:
            output_dir = Path("artifacts") / "template_analysis" / template_id
            debug_info = build_visual_debug_report(template_name, visual_model, manifest, output_dir)
            manifest["debug"].update(debug_info)

            # Additional logging required by acceptance criteria
            print(f"[TemplateAnalysis] visual_regions_count={debug_info.get('visual_regions_count', 0)}")
            print(f"[TemplateAnalysis] visual_tables_count={debug_info.get('visual_tables_count', 0)}")
            label_value_rows = sum(1 for t in visual_model.tables for r in t.rows if r.role == 'label_value_row')
            print(f"[TemplateAnalysis] label_value_rows_count={label_value_rows}")
            mailmerge_regions = sum(1 for r in visual_model.regions if r.region_type == 'mailmerge_table_region')
            print(f"[TemplateAnalysis] mailmerge_regions_count={mailmerge_regions}")
            instruction_regions = sum(1 for r in visual_model.regions if r.region_type == 'instruction_region')
            print(f"[TemplateAnalysis] instruction_regions_count={instruction_regions}")

            print(f"[TemplateAnalysis] visual_debug_html_path={debug_info.get('visual_debug_html_path', '')}")
            print(f"[TemplateAnalysis] raw_visual_tokens_count={debug_info.get('raw_visual_tokens_count', 0)}")
            print(f"[TemplateAnalysis] manifest_token_count={debug_info.get('manifest_token_count', 0)}")
            print(f"[TemplateAnalysis] ignored_control_tokens={debug_info.get('ignored_control_tokens', [])}")


    return GraphResult(status=JobStatus.COMPLETED, data=manifest)
