from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, StateGraph

from src.shared.models import GraphResult, JobStatus
from src.shared.storage import object_store
from src.worker.agentic_core import AgenticCore
from src.worker.agents.template_analysis.extractors import (
    extract_docling_layout_evidence,
    extract_openxml_evidence,
    extract_python_docx_evidence,
    extract_visual_layout_evidence,
    reconcile_template_evidence,
)
from src.worker.agents.template_analysis.field_candidate_builder import build_field_candidates_from_evidence
from src.worker.agents.template_analysis.manifest_critic import critique_manifest_against_evidence
from src.worker.agents.template_analysis.manifest_validator import validate_manifest_fields_against_layout


logger = logging.getLogger(__name__)
TEMPLATE_ANALYSIS_PIPELINE_VERSION = "layout_v2_agentic_qc_2026_05_28"
PIPELINE_VERSION = TEMPLATE_ANALYSIS_PIPELINE_VERSION


class TemplateAnalysisState(TypedDict):
    template_id: str
    template_name: str
    template_object_key: str
    template_bytes: bytes
    evidence: dict[str, Any]
    layout: dict[str, Any]
    field_candidates: list[dict[str, Any]]
    fields: list[dict[str, Any]]


def _load_template_bytes(state: TemplateAnalysisState) -> TemplateAnalysisState:
    state["template_bytes"] = object_store.get_bytes(state["template_object_key"])
    return state


def _extract_evidence(state: TemplateAnalysisState) -> TemplateAnalysisState:
    logger.info("[TemplateAnalysis] pipeline_version=%s", PIPELINE_VERSION)
    logger.info("[TemplateAnalysis] graph_file=src/worker/agents/template_analysis/graph.py")
    tb = state["template_bytes"]
    ox = extract_openxml_evidence(tb)
    pd = extract_python_docx_evidence(tb)
    dl = extract_docling_layout_evidence(tb, state.get("template_name") or "template.docx")
    vl = extract_visual_layout_evidence(tb)
    state["layout"] = reconcile_template_evidence(ox, pd, dl, vl)
    state["evidence"] = {"openxml": ox, "python_docx": pd, "docling": dl, "visual": vl}
    return state


def _build_candidates(state: TemplateAnalysisState) -> TemplateAnalysisState:
    state["field_candidates"] = build_field_candidates_from_evidence(state["layout"])
    return state


def _plan_and_validate(state: TemplateAnalysisState) -> TemplateAnalysisState:
    agentic = AgenticCore()
    planned = agentic.plan_manifest_from_evidence(
        template_name=state["template_name"],
        canonical_blocks=state["layout"].get("canonical_blocks", []),
        field_candidates=state.get("field_candidates", []),
        repeat_groups=state["layout"].get("repeat_groups", []),
    )
    planned_fields = planned.get("fields", [])
    validated = validate_manifest_fields_against_layout(planned_fields, {"blocks": state["layout"].get("canonical_blocks", [])})
    critique = critique_manifest_against_evidence({"fields": validated}, state["layout"])
    if not critique["passed"]:
        validated = validate_manifest_fields_against_layout(validated, {"blocks": state["layout"].get("canonical_blocks", [])})
    state["fields"] = validated
    logger.info("[TemplateAnalysis] manifest_version=2")
    logger.info("[TemplateAnalysis] blocks_count=%s", len(state["layout"].get("canonical_blocks", [])))
    logger.info("[TemplateAnalysis] repeat_groups_count=%s", len(state["layout"].get("repeat_groups", [])))
    logger.info("[TemplateAnalysis] fields_count=%s", len(validated))
    logger.info("[TemplateAnalysis] rejected_fields_count=%s", max(0, len(planned_fields) - len(validated)))
    return state


def build_template_analysis_graph():
    graph = StateGraph(TemplateAnalysisState)
    graph.add_node("load_template_bytes", _load_template_bytes)
    graph.add_node("extract_evidence", _extract_evidence)
    graph.add_node("build_candidates", _build_candidates)
    graph.add_node("plan_and_validate", _plan_and_validate)
    graph.set_entry_point("load_template_bytes")
    graph.add_edge("load_template_bytes", "extract_evidence")
    graph.add_edge("extract_evidence", "build_candidates")
    graph.add_edge("build_candidates", "plan_and_validate")
    graph.add_edge("plan_and_validate", END)
    return graph.compile()


def run_template_analysis(template_id: str, template_name: str, template_object_key: str) -> GraphResult:
    print(f"[TemplateAnalysis] pipeline_version={TEMPLATE_ANALYSIS_PIPELINE_VERSION}")
    print(f"[TemplateAnalysis] graph_module={__file__}")
    
    app = build_template_analysis_graph()
    result = app.invoke({"template_id": template_id, "template_name": template_name, "template_object_key": template_object_key, "template_bytes": b"", "evidence": {}, "layout": {}, "field_candidates": [], "fields": []})
    manifest = {
        "manifest_id": str(uuid4()), "template_id": template_id, "version": 2, "manifest_schema": "template_manifest_v2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "layout": {"blocks_count": len(result.get("layout", {}).get("canonical_blocks", [])), "repeat_groups_count": len(result.get("layout", {}).get("repeat_groups", []))},
        "fields": result.get("fields", []),
    }
    
    from src.shared.config import settings
    if settings.app_env != "production":
        manifest["debug"] = {
            "pipeline_version": TEMPLATE_ANALYSIS_PIPELINE_VERSION,
            "graph_module": __file__,
            "blocks_count": len(result.get("layout", {}).get("canonical_blocks", [])),
            "fields_count": len(result.get("fields", [])),
        }
        
    print(f"[TemplateAnalysis] manifest_version={manifest['version']}")
    print(f"[TemplateAnalysis] manifest_schema={manifest.get('manifest_schema')}")
    print(f"[TemplateAnalysis] blocks_count={len(result.get('layout', {}).get('canonical_blocks', []))}")
    print(f"[TemplateAnalysis] fields_count={len(result.get('fields', []))}")
    
    return GraphResult(status=JobStatus.COMPLETED, data=manifest)
