from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, StateGraph

from src.shared.models import GraphResult, JobStatus
from src.shared.storage import object_store
from src.worker.agentic_core import AgenticCore
from src.worker.agents.template_analysis.layout_extractor import extract_layout_blocks_from_docx
from src.worker.agents.template_analysis.manifest_validator import validate_manifest_fields_against_layout


class TemplateAnalysisState(TypedDict):
    template_id: str
    template_name: str
    template_object_key: str
    template_bytes: bytes
    layout: dict[str, Any]
    fields: list[dict[str, Any]]


def _slug(s: str) -> str:
    import re
    return re.sub(r"[^a-zA-Z0-9]+", "_", (s or "").strip()).strip("_").lower() or "field"


def _load_template_bytes(state: TemplateAnalysisState) -> TemplateAnalysisState:
    state["template_bytes"] = object_store.get_bytes(state["template_object_key"])
    return state


def _extract_layout_blocks(state: TemplateAnalysisState) -> TemplateAnalysisState:
    state["layout"] = extract_layout_blocks_from_docx(state["template_bytes"])
    return state


def _build_grouped_section_fields(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: list[dict[str, Any]] = []

    by_section: dict[str, list[dict[str, Any]]] = {}
    for b in blocks:
        section = (b.get("section_heading") or "").strip()
        by_section.setdefault(section, []).append(b)

    def mk_sub(name: str, token: str, hint: str, field_type: str = "scalar") -> dict[str, Any]:
        return {"name": name, "field_type": field_type, "template_token": token, "source_hint": hint}

    for section, items in by_section.items():
        s = section.lower()
        item_tokens = [str(i.get("placeholder_text") or i.get("raw_token") or "") for i in items]
        source_ids = [i.get("block_id") for i in items if i.get("block_id")]

        if "work experience" in s:
            sub = []
            if any("[job description, date]" in t.lower() for t in item_tokens):
                sub.append(mk_sub("job_description_date", "[Job description, Date]", "Job title/description and date"))
            if any("[organisation]" in t.lower() for t in item_tokens):
                sub.append(mk_sub("organisation", "[Organisation]", "Organisation name"))
            if any("[bullet point responsibilities]" in t.lower() for t in item_tokens):
                sub.append(mk_sub("responsibilities", "[Bullet point responsibilities]", "Responsibilities bullets", "array"))
            if sub:
                grouped.append({
                    "name": "work_experience",
                    "display_label": "Work Experience",
                    "field_type": "array_object",
                    "source_classification": "resume_fact",
                    "template_token": "[Job description, Date]",
                    "source_block_ids": source_ids,
                    "sub_fields": sub,
                    "template_evidence": {"section_heading": section, "evidence_text": " | ".join(item_tokens)},
                    "render_contract": {"render_strategy": "repeat_block", "anchor_token": "[Job description, Date]"},
                })

        if s == "education" or "education" in s:
            sub = []
            if any("[institution, date]" in t.lower() for t in item_tokens):
                sub.append(mk_sub("institution_date", "[Institution, Date]", "Institution and date"))
            if any("[bullet point grades]" in t.lower() for t in item_tokens):
                sub.append(mk_sub("grades", "[Bullet point grades]", "Grades bullets", "array"))
            if sub:
                grouped.append({
                    "name": "education",
                    "display_label": "Education",
                    "field_type": "array_object",
                    "source_classification": "resume_fact",
                    "template_token": "[Institution, Date]",
                    "source_block_ids": source_ids,
                    "sub_fields": sub,
                    "template_evidence": {"section_heading": section, "evidence_text": " | ".join(item_tokens)},
                    "render_contract": {"render_strategy": "repeat_block", "anchor_token": "[Institution, Date]"},
                })

        if "interests" in s and any("[bullet point list]" in t.lower() for t in item_tokens):
            grouped.append({
                "name": "interests_and_activities",
                "display_label": "Interests and Activities",
                "field_type": "array",
                "source_classification": "resume_fact",
                "template_token": "[Bullet point list]",
                "source_block_ids": source_ids,
                "template_evidence": {"section_heading": section, "evidence_text": " | ".join(item_tokens)},
                "render_contract": {"render_strategy": "bullet_list_replace", "anchor_token": "[Bullet point list]"},
            })

    return grouped


def _infer_manifest_fields_from_layout(state: TemplateAnalysisState) -> TemplateAnalysisState:
    blocks = state["layout"].get("blocks", [])
    llm_blocks = [{k: b.get(k) for k in ("block_id", "section_heading", "label_text", "placeholder_text", "raw_token", "evidence_text")} for b in blocks]
    agentic = AgenticCore()
    fields = []
    try:
        inferred = agentic.infer_template_manifest_fields(
            template_name=state["template_name"],
            tokens=[{"name": b.get("block_id", ""), "template_token": b.get("raw_token", "")} for b in llm_blocks],
            template_text=str(llm_blocks),
        )
        for f in inferred:
            if not f.get("source_block_ids"):
                continue
            fields.append(f)
    except Exception:
        pass

    if not fields:
        fields.extend(_build_grouped_section_fields(blocks))
        covered = {bid for f in fields for bid in (f.get("source_block_ids") or [])}
        for b in blocks:
            if b.get("block_id") in covered:
                continue
            token = b.get("placeholder_text") or b.get("raw_token") or ""
            label = b.get("label_text") or b.get("section_heading") or token
            name = _slug(label)
            fields.append({
                "name": name,
                "display_label": label,
                "field_type": "array" if b.get("is_bullet") else "scalar",
                "source_classification": "recruiter_input" if token.startswith("[") else "resume_fact",
                "template_token": token,
                "source_block_ids": [b.get("block_id")],
                "template_evidence": {
                    "section_heading": b.get("section_heading"),
                    "label_text": b.get("label_text"),
                    "placeholder_text": b.get("placeholder_text"),
                    "evidence_text": b.get("evidence_text"),
                },
                "render_contract": {
                    "render_strategy": "mergefield_replace" if str(token).upper().startswith("MERGEFIELD") else "placeholder_replace",
                    "anchor_token": token,
                    "occurrence_selector": {
                        "source_block_id": b.get("block_id"),
                        "occurrence_index": b.get("occurrence_index"),
                        "label_text": b.get("label_text"),
                    },
                },
            })
    state["fields"] = fields
    return state


def _validate_manifest_fields(state: TemplateAnalysisState) -> TemplateAnalysisState:
    state["fields"] = validate_manifest_fields_against_layout(state.get("fields", []), state.get("layout", {}))
    return state


def build_template_analysis_graph():
    graph = StateGraph(TemplateAnalysisState)
    graph.add_node("load_template_bytes", _load_template_bytes)
    graph.add_node("extract_layout_blocks", _extract_layout_blocks)
    graph.add_node("infer_manifest_fields_from_layout", _infer_manifest_fields_from_layout)
    graph.add_node("validate_manifest_fields", _validate_manifest_fields)
    graph.set_entry_point("load_template_bytes")
    graph.add_edge("load_template_bytes", "extract_layout_blocks")
    graph.add_edge("extract_layout_blocks", "infer_manifest_fields_from_layout")
    graph.add_edge("infer_manifest_fields_from_layout", "validate_manifest_fields")
    graph.add_edge("validate_manifest_fields", END)
    return graph.compile()


def run_template_analysis(template_id: str, template_name: str, template_object_key: str) -> GraphResult:
    app = build_template_analysis_graph()
    result = app.invoke({"template_id": template_id, "template_name": template_name, "template_object_key": template_object_key, "template_bytes": b"", "layout": {}, "fields": []})
    layout = result.get("layout", {})
    manifest = {
        "manifest_id": str(uuid4()),
        "template_id": template_id,
        "version": 2,
        "manifest_schema": "template_manifest_v2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "layout": {
            "blocks_count": len(layout.get("blocks", [])),
            "repeat_groups_count": len(layout.get("repeat_groups", [])),
        },
        "fields": result.get("fields", []),
    }
    return GraphResult(status=JobStatus.COMPLETED, data=manifest)
