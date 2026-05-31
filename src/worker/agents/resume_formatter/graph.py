from __future__ import annotations

from typing import Any, TypedDict
from uuid import uuid4
from datetime import datetime, timezone

from langgraph.graph import END, StateGraph

from src.shared.models import GraphResult, JobStatus
from src.worker.agentic_core import AgenticCore
from src.worker.agents.resume_formatter.template_suggestion import TemplateSuggestionService
from src.worker.agents.resume_formatter.injector import inject_render_payload_into_docx
from src.worker.agents.resume_formatter.render_payload_builder import build_filled_template_payload


class ResumeFormatState(TypedDict):
    job_id: str
    template_id: str | None
    resume_text: str | None
    resume_object_key: str | None
    raw_resume_text: str | None
    suggested_templates: list[dict]
    manifest: dict[str, Any] | None
    mapping_result: dict[str, Any]
    render_payload: dict[str, Any]
    extracted: dict[str, Any]
    filled_manifest: dict[str, Any] | None
    rendered_bytes: bytes | None
    status: JobStatus
    error: str | None


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

def load_resume_input(state: ResumeFormatState) -> ResumeFormatState:
    from src.shared.storage import object_store
    from src.shared.extractor import extract_text_from_bytes

    if state.get("resume_text"):
        state["raw_resume_text"] = state["resume_text"]
    elif state.get("resume_object_key"):
        try:
            resume_bytes = object_store.get_bytes(state["resume_object_key"])
            state["raw_resume_text"] = extract_text_from_bytes(resume_bytes, filename=state["resume_object_key"])
            print(f"[LoadResumeInput] Extracted {len(state['raw_resume_text'])} chars from {state['resume_object_key']}")
        except Exception as e:
            state["status"] = JobStatus.FAILED
            state["error"] = f"Failed to extract resume text from S3: {e}"
    else:
        state["status"] = JobStatus.FAILED
        state["error"] = "Missing resume_text or resume_object_key in input payload"
    return state


def resolve_or_suggest_template(state: ResumeFormatState) -> ResumeFormatState:
    if state.get("status") == JobStatus.FAILED:
        return state
    if state.get("template_id"):
        return state
    raw_text = state.get("raw_resume_text") or ""
    state["suggested_templates"] = TemplateSuggestionService.suggest_templates(raw_text)
    state["status"] = JobStatus.WAITING_FOR_TEMPLATE_SELECTION
    return state


def load_template_manifest(state: ResumeFormatState) -> ResumeFormatState:
    if state.get("status") in [JobStatus.FAILED, JobStatus.WAITING_FOR_TEMPLATE_SELECTION]:
        return state
    from src.shared.repository import repo
    template_id = state["template_id"]
    manifest = repo.get_manifest(template_id)
    if not manifest:
        print(f"[LoadManifest] WARNING: No manifest for template_id={template_id}")
        state["manifest"] = {"fields": []}
    else:
        fields = manifest.get("fields", [])
        print(f"[LoadManifest] Loaded {len(fields)} fields")
        # Log injection_details availability
        with_details = sum(1 for f in fields if f.get("injection_details"))
        print(f"[LoadManifest] {with_details}/{len(fields)} fields have injection_details stored")
        state["manifest"] = manifest
    return state


def map_resume_to_manifest(state: ResumeFormatState) -> ResumeFormatState:
    if state.get("status") in [JobStatus.FAILED, JobStatus.WAITING_FOR_TEMPLATE_SELECTION]:
        return state

    manifest = state.get("manifest") or {"fields": []}
    fields = manifest.get("fields", [])
    raw_text = state.get("raw_resume_text") or ""

    print(f"[ExtractData] Extracting values for {len(fields)} manifest fields...")
    agentic_core = AgenticCore()
    try:
        extracted = agentic_core.extract_resume_fields(
            fields=fields,
            resume_text=raw_text,
            use_strong_model=True,
        )
        print(f"[ExtractData] Extracted {len(extracted)} fields: {list(extracted.keys())}")
    except Exception as e:
        print(f"[ExtractData] LLM extraction failed ({e}), using heuristic fallback")
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        extracted = {"field_mappings": {
            "candidate_name": {"value": lines[0] if lines else "Unknown Candidate"},
            "candidate_fullname": {"value": lines[0] if lines else "Unknown Candidate"},
            "candidate_email": {"value": next((x for x in lines if "@" in x), "")},
        }}

    state["mapping_result"] = extracted
    
    # Ensure candidate_own_cv is populated with the original resume text
    field_mappings = extracted.setdefault("field_mappings", {})
    if "candidate_own_cv" in [f.get("name") for f in fields]:
        if "candidate_own_cv" not in field_mappings or field_mappings["candidate_own_cv"].get("value") is None:
            field_mappings["candidate_own_cv"] = {
                "value": raw_text,
                "status": "mapped",
                "confidence": 1.0,
                "source": {"page": 1, "section": "Original CV", "evidence_text": "Full original resume text injected."}
            }

    state["extracted"] = {k: v.get("value") for k, v in field_mappings.items()}
    return state


def build_render_payload(state: ResumeFormatState) -> ResumeFormatState:
    if state.get("status") in [JobStatus.FAILED, JobStatus.WAITING_FOR_TEMPLATE_SELECTION]:
        return state
    manifest = state.get("manifest") or {"fields": []}
    mapping_result = state.get("mapping_result") or {}
    payload = build_filled_template_payload(manifest, mapping_result)
    state["render_payload"] = payload
    state["filled_manifest"] = {
        "manifest_id": manifest.get("manifest_id", str(uuid4())),
        "template_id": state.get("template_id"),
        "filled_at": datetime.now(timezone.utc).isoformat(),
        "manifest": manifest,
        "fields": manifest.get("fields", []),
        "filled_values": state.get("extracted", {}),
        "mapping_result": mapping_result,
        "render_payload": payload,
    }
    return state


def render_resume(state: ResumeFormatState) -> ResumeFormatState:
    if state.get("status") in [JobStatus.FAILED, JobStatus.WAITING_FOR_TEMPLATE_SELECTION]:
        return state

    template_id = state["template_id"]
    payload = state.get("render_payload") or {}
    manifest = state.get("manifest") or {"fields": []}
    manifest_fields = manifest.get("fields", [])

    from src.shared.repository import repo
    from src.shared.storage import object_store

    template = repo.get_template(template_id)
    if not template:
        state["status"] = JobStatus.FAILED
        state["error"] = f"Template with ID {template_id} not found"
        return state

    try:
        template_bytes = object_store.get_bytes(template["object_key"])
        print("[RenderResume] Injecting deterministic render payload into template...")
        docx_bytes = inject_render_payload_into_docx(template_bytes, payload, manifest)
        state["rendered_bytes"] = docx_bytes
        state["status"] = JobStatus.COMPLETED
        print(f"[RenderResume] Rendered DOCX: {len(docx_bytes)} bytes")
    except Exception as e:
        state["status"] = JobStatus.FAILED
        state["error"] = f"Failed to render DOCX: {e}"
        import traceback
        print(traceback.format_exc())

    return state


# ---------------------------------------------------------------------------
# Routing + Graph assembly
# ---------------------------------------------------------------------------

def route_after_suggest(state: ResumeFormatState) -> str:
    if state.get("status") == JobStatus.FAILED:
        return END
    if state.get("status") == JobStatus.WAITING_FOR_TEMPLATE_SELECTION:
        return END
    return "load_template_manifest"


def build_resume_format_graph():
    graph = StateGraph(ResumeFormatState)
    graph.add_node("load_resume_input", load_resume_input)
    graph.add_node("resolve_or_suggest_template", resolve_or_suggest_template)
    graph.add_node("load_template_manifest", load_template_manifest)
    graph.add_node("map_resume_to_manifest", map_resume_to_manifest)
    graph.add_node("build_render_payload", build_render_payload)
    graph.add_node("render_resume", render_resume)

    graph.set_entry_point("load_resume_input")
    graph.add_edge("load_resume_input", "resolve_or_suggest_template")
    graph.add_conditional_edges(
        "resolve_or_suggest_template",
        route_after_suggest,
        {"load_template_manifest": "load_template_manifest", END: END},
    )
    graph.add_edge("load_template_manifest", "map_resume_to_manifest")
    graph.add_edge("map_resume_to_manifest", "build_render_payload")
    graph.add_edge("build_render_payload", "render_resume")
    graph.add_edge("render_resume", END)
    return graph.compile()


def run_resume_format(
    job_id: str,
    template_id: str | None,
    resume_text: str | None = None,
    resume_object_key: str | None = None,
) -> GraphResult:
    app = build_resume_format_graph()
    result = app.invoke(
        {
            "job_id": job_id,
            "template_id": template_id,
            "resume_text": resume_text,
            "resume_object_key": resume_object_key,
            "raw_resume_text": None,
            "suggested_templates": [],
            "manifest": None,
            "mapping_result": {},
            "render_payload": {},
            "extracted": {},
            "filled_manifest": None,
            "rendered_bytes": None,
            "status": JobStatus.QUEUED,
            "error": None,
        }
    )

    return GraphResult(
        status=result.get("status", JobStatus.FAILED),
        data={
            "job_id": job_id,
            "template_id": result.get("template_id"),
            "resume_text": result.get("raw_resume_text"),
            "resume_object_key": result.get("resume_object_key"),
            "suggested_templates": result.get("suggested_templates", []),
            "extracted": result.get("extracted", {}),
            "filled_manifest": result.get("filled_manifest"),
            "rendered_bytes": result.get("rendered_bytes"),
        },
        error=result.get("error"),
    )
