from __future__ import annotations

from typing import Any, TypedDict
from uuid import uuid4
from datetime import datetime, timezone
import re

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
    resume_summary: str | None
    suggested_templates: list[dict]
    manifest: dict[str, Any] | None
    resume_fact_fields: list[dict[str, Any]]
    generated_fields: list[dict[str, Any]]
    input_only_fields: list[dict[str, Any]]
    recruiter_input_fields: list[dict[str, Any]]
    ats_input_fields: list[dict[str, Any]]
    resume_fact_result: dict[str, Any]
    generated_result: dict[str, Any]
    recruiter_input_result: dict[str, Any]
    ats_input_result: dict[str, Any]
    mapping_result: dict[str, Any]
    render_payload: dict[str, Any]
    extracted: dict[str, Any]
    filled_manifest: dict[str, Any] | None
    rendered_bytes: bytes | None
    status: JobStatus
    error: str | None


def _is_empty_mapped_value(value: Any) -> bool:
    return value in (None, "", [])


def _first_non_empty_resume_lines(raw_resume_text: str, limit: int = 12) -> list[str]:
    lines = [line.strip(" -\t") for line in raw_resume_text.splitlines() if line.strip()]
    return lines[:limit]


def _extract_name_candidate(raw_resume_text: str) -> str | None:
    email_re = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    phone_re = re.compile(r"\+?\d[\d\s()\-]{6,}\d")
    for line in _first_non_empty_resume_lines(raw_resume_text, limit=8):
        if email_re.search(line) or phone_re.search(line):
            continue
        if len(line) < 3 or len(line) > 70:
            continue
        # Prefer title-case looking lines for candidate names.
        alpha_words = [w for w in re.split(r"\s+", line) if w.isalpha()]
        if len(alpha_words) >= 2:
            return line
    return None


def _collect_section_lines(raw_resume_text: str, heading_terms: list[str], max_lines: int = 8) -> list[str]:
    lines = [line.strip() for line in raw_resume_text.splitlines()]
    if not lines:
        return []

    lowered_headings = [t.lower() for t in heading_terms]
    collected: list[str] = []
    in_section = False

    def _looks_like_new_heading(text: str) -> bool:
        if not text:
            return False
        if text.endswith(":"):
            return True
        if len(text) > 60:
            return False

        words = re.findall(r"[A-Za-z][A-Za-z'&/\-]*", text)
        if not words or len(words) > 7:
            return False

        if text.isupper():
            return True

        skip = {"and", "or", "of", "in", "to", "for", "the", "a", "an", "with"}
        significant = [w for w in words if w.lower() not in skip]
        return bool(significant) and all(w[0].isupper() for w in significant)

    for line in lines:
        normalized = re.sub(r"\s+", " ", line).strip()
        low = normalized.lower()
        if not normalized:
            if in_section and collected:
                break
            continue

        is_new_heading = any(h in low for h in lowered_headings)
        looks_like_heading = _looks_like_new_heading(normalized)

        if is_new_heading:
            in_section = True
            continue

        if in_section and looks_like_heading:
            # Keep likely content rows (for example education/employment entries)
            # even when they are title-cased, if they carry content signals.
            has_content_signal = bool(
                re.search(r"\b(?:19|20)\d{2}\b", normalized)
                or "," in normalized
                or " - " in normalized
                or " at " in low
            )
            if not has_content_signal:
                break

        if in_section:
            item = normalized.lstrip("-•* ").strip()
            if item:
                collected.append(item)
            if len(collected) >= max_lines:
                break

    return collected


def _extract_skills(raw_resume_text: str) -> list[str]:
    skill_lines = _collect_section_lines(
        raw_resume_text,
        ["key skills", "skills", "core skills", "technical skills", "competencies", "expertise"],
        max_lines=10,
    )
    if not skill_lines:
        return []

    skills: list[str] = []
    for line in skill_lines:
        parts = [p.strip() for p in re.split(r"[,|;]", line) if p.strip()]
        if len(parts) > 1:
            skills.extend(parts)
        else:
            skills.append(line)

    deduped: list[str] = []
    seen: set[str] = set()
    for skill in skills:
        key = skill.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(skill)
    return deduped[:12]


def _extract_qualifications(raw_resume_text: str) -> list[str]:
    qual_lines = _collect_section_lines(
        raw_resume_text,
        [
            "professional qualifications",
            "professional qualification",
            "qualifications",
            "qualification",
            "certifications",
            "certification",
            "certificates",
            "certificate",
            "accreditation",
            "accreditations",
            "courses",
        ],
        max_lines=10,
    )

    if not qual_lines:
        # Fallback for CV formats that list certifications inline without a dedicated section.
        for raw_line in raw_resume_text.splitlines():
            normalized = raw_line.strip().lstrip("-•* ").strip()
            if not normalized:
                continue
            low = normalized.lower()
            if any(k in low for k in ("certified", "certification", "certificate", "accredit")):
                qual_lines.append(normalized)

    deduped: list[str] = []
    seen: set[str] = set()
    for qual in qual_lines:
        key = qual.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(qual)

    return deduped[:8]


def _array_object_item_key(field: dict[str, Any]) -> str:
    sub_fields = field.get("sub_fields")
    if isinstance(sub_fields, list):
        for sf in sub_fields:
            key = str((sf or {}).get("name") or "").strip()
            if key:
                return key
    return "value"


def _normalize_array_object_value(field: dict[str, Any], value: Any) -> list[dict[str, Any]]:
    primary_key = _array_object_item_key(field)

    if isinstance(value, dict):
        return [value]

    if isinstance(value, list):
        normalized: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                normalized.append(item)
            elif isinstance(item, str) and item.strip():
                normalized.append({primary_key: item.strip()})
        return normalized

    if isinstance(value, str) and value.strip():
        return [{primary_key: value.strip()}]

    return []


def _heuristic_array_object_value(field: dict[str, Any], raw_resume_text: str) -> list[dict[str, Any]]:
    heading_terms: list[str] = []
    heading_sources: list[str] = [
        str(field.get("display_label") or ""),
        str(field.get("source_hint") or ""),
        str(field.get("name") or "").replace("_", " "),
        str((field.get("template_evidence") or {}).get("section_heading") or ""),
        str(field.get("template_token") or "").replace("_", " "),
    ]

    for sub_field in field.get("sub_fields") or []:
        if not isinstance(sub_field, dict):
            continue
        heading_sources.append(str(sub_field.get("display_label") or ""))
        heading_sources.append(str(sub_field.get("name") or "").replace("_", " "))
        heading_sources.append(str(sub_field.get("template_token") or "").replace("_", " "))

    stop_words = {
        "and",
        "the",
        "for",
        "with",
        "from",
        "that",
        "this",
        "type",
        "text",
        "bullet",
        "point",
        "list",
    }

    seen_terms: set[str] = set()
    for source in heading_sources:
        cleaned = re.sub(r"[^a-zA-Z0-9\s]+", " ", source).strip().lower()
        if not cleaned:
            continue

        if len(cleaned) >= 4 and cleaned not in stop_words and cleaned not in seen_terms:
            heading_terms.append(cleaned)
            seen_terms.add(cleaned)

        for token in cleaned.split():
            if len(token) < 6 or token in stop_words or token in seen_terms:
                continue
            heading_terms.append(token)
            seen_terms.add(token)

    if not heading_terms:
        return []

    lines = _collect_section_lines(raw_resume_text, heading_terms, max_lines=24)
    if not lines:
        return []

    sub_fields = field.get("sub_fields") or []
    sub_names = [str((sf or {}).get("name") or "").strip() for sf in sub_fields if isinstance(sf, dict)]
    primary_key = _array_object_item_key(field)

    list_like_sub_field = None
    for sf in sub_fields:
        if not isinstance(sf, dict):
            continue
        name = str(sf.get("name") or "").strip()
        sf_type = str(sf.get("field_type") or "").lower()
        if sf_type == "array" or any(term in name.lower() for term in ("bullet", "responsibilit", "dutie", "grade", "achievement")):
            list_like_sub_field = name
            break

    organisation_key = next((n for n in sub_names if "organisation" in n.lower() or "company" in n.lower() or "employer" in n.lower()), None)

    rows: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    date_re = re.compile(r"\b(?:19|20)\d{2}\b|\b(?:present|current)\b", re.IGNORECASE)

    for line in lines:
        text = re.sub(r"\s+", " ", line).strip()
        if not text:
            continue

        starts_new = current is None or bool(date_re.search(text))
        if not starts_new and len(text) <= 72 and any(sep in text.lower() for sep in (" at ", " - ", " | ")):
            starts_new = True

        if starts_new:
            if current:
                rows.append(current)
            current = {primary_key: text}

            if organisation_key and " at " in text.lower():
                org = text.split(" at ", 1)[1].strip(" -|, ")
                if org:
                    current[organisation_key] = org
            continue

        if current is None:
            current = {primary_key: text}
            continue

        if list_like_sub_field:
            arr = current.setdefault(list_like_sub_field, [])
            if isinstance(arr, list):
                arr.append(text)

    if current:
        rows.append(current)

    return rows


def _heuristic_value_for_field(field: dict[str, Any], raw_resume_text: str) -> Any:
    semantic = " ".join(
        str(field.get(k) or "")
        for k in ("name", "display_label", "source_hint", "template_token")
    ).lower()
    field_type = str(field.get("field_type") or "scalar").lower()

    if field_type == "array_object":
        rows = _heuristic_array_object_value(field, raw_resume_text)
        if rows:
            return rows

    if "full name" in semantic or ("name" in semantic and any(t in semantic for t in ("candidate", "person", "profile"))):
        return _extract_name_candidate(raw_resume_text)

    if "skill" in semantic:
        skills = _extract_skills(raw_resume_text)
        if not skills:
            return None
        if field_type.startswith("array"):
            return skills
        return ", ".join(skills)

    if any(term in semantic for term in ("professional_qualification", "professional qualification", "certification", "qualification")):
        quals = _extract_qualifications(raw_resume_text)
        if not quals:
            return None
        if field_type.startswith("array"):
            if field_type == "array_object":
                item_key = _array_object_item_key(field)
                return [{item_key: q} for q in quals]
            return quals
        return ", ".join(quals)

    if "notice" in semantic:
        match = re.search(r"(immediate|\d+\s*(?:day|week|month)s?)", raw_resume_text, flags=re.IGNORECASE)
        return match.group(1).strip() if match else None

    if "salary" in semantic:
        match = re.search(r"(?:£|\$|EUR|INR|Rs\.?)[\s]*[0-9][0-9,\.]*", raw_resume_text, flags=re.IGNORECASE)
        return match.group(0).strip() if match else None

    if any(term in semantic for term in ("town", "city", "location")):
        lines = _first_non_empty_resume_lines(raw_resume_text, limit=10)
        for line in lines:
            if re.search(r"\b(?:london|manchester|birmingham|leeds|bristol|glasgow)\b", line, flags=re.IGNORECASE):
                return line

    return None


def _apply_heuristic_resume_fact_fallback(
    *,
    fields: list[dict[str, Any]],
    field_mappings: dict[str, Any],
    raw_resume_text: str,
) -> int:
    applied = 0
    for field in fields:
        name = str(field.get("name") or "").strip()
        if not name:
            continue
        existing_value = (field_mappings.get(name) or {}).get("value")
        if not _is_empty_mapped_value(existing_value):
            continue

        heuristic_value = _heuristic_value_for_field(field, raw_resume_text)
        if _is_empty_mapped_value(heuristic_value):
            continue

        field_mappings[name] = {
            "value": heuristic_value,
            "status": "mapped",
            "confidence": 0.45,
            "source": {
                "page": 1,
                "section": "Heuristic Fallback",
                "evidence_text": "Recovered from deterministic resume parsing fallback.",
            },
        }
        applied += 1
    return applied


def _normalize_and_backfill_array_object_fields(
    *,
    fields: list[dict[str, Any]],
    field_mappings: dict[str, Any],
    raw_resume_text: str,
) -> int:
    applied = 0
    for field in fields:
        field_type = str(field.get("field_type") or "scalar").lower()
        if field_type != "array_object":
            continue

        name = str(field.get("name") or "").strip()
        if not name:
            continue

        entry = field_mappings.get(name) or {}
        existing_value = entry.get("value")
        normalized_existing = _normalize_array_object_value(field, existing_value)
        if normalized_existing:
            if normalized_existing != existing_value:
                field_mappings[name] = {
                    **entry,
                    "value": normalized_existing,
                    "status": "mapped",
                    "confidence": max(float(entry.get("confidence") or 0.0), 0.5),
                }
                applied += 1
            continue

        fallback_rows = _heuristic_array_object_value(field, raw_resume_text)
        if not fallback_rows:
            continue

        field_mappings[name] = {
            "value": fallback_rows,
            "status": "mapped",
            "confidence": 0.45,
            "source": {
                "page": 1,
                "section": "Heuristic Array Fallback",
                "evidence_text": "Recovered repeatable entries from resume section headings.",
            },
        }
        applied += 1

    return applied


def _is_instruction_resume_field(field: dict[str, Any]) -> bool:
    render_strategy = str((field.get("render_contract") or {}).get("render_strategy") or "").strip().lower()
    if render_strategy == "remove_instruction_text":
        return True

    evidence = field.get("template_evidence") or {}
    region_type = str(evidence.get("region_type") or "").strip().lower()
    if region_type == "instruction_region":
        return True

    text_probe = " ".join(
        str(field.get(k) or "")
        for k in ("name", "display_label", "template_token", "source_hint")
    ).lower()
    return any(
        marker in text_probe
        for marker in (
            "candidate own cv",
            "candidate's own cv",
            "original cv",
            "paste cv",
            "full resume",
            "resume text",
        )
    )


def _apply_instruction_resume_fields(
    *,
    manifest_fields: list[dict[str, Any]],
    field_mappings: dict[str, dict[str, Any]],
    raw_resume_text: str,
) -> int:
    if not raw_resume_text.strip():
        return 0

    applied = 0
    for field in manifest_fields:
        if not isinstance(field, dict):
            continue
        if not _is_instruction_resume_field(field):
            continue

        name = str(field.get("name") or "").strip()
        if not name:
            continue

        field_mappings[name] = {
            "value": raw_resume_text,
            "status": "mapped",
            "confidence": 1.0,
            "source": {
                "page": 1,
                "section": "Original CV",
                "evidence_text": "Full original resume text injected for instruction field.",
            },
        }
        applied += 1

    return applied


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


def create_resume_summary(state: ResumeFormatState) -> ResumeFormatState:
    if state.get("status") == JobStatus.FAILED:
        return state

    raw_text = (state.get("raw_resume_text") or "").strip()
    if not raw_text:
        state["resume_summary"] = None
        return state

    try:
        agentic_core = AgenticCore()
        summary = agentic_core.summarize_resume(
            resume_text=raw_text,
            use_strong_model=True,
        )
        if summary:
            state["resume_summary"] = summary
            return state
    except Exception as e:
        print(f"[ResumeSummary] LLM summary generation failed ({e}), using deterministic fallback")

    # Safe fallback when LLM is unavailable.
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    lead = _extract_name_candidate(raw_text) or (lines[0] if lines else "Candidate")
    highlights = []
    skills = _extract_skills(raw_text)
    if skills:
        highlights.append(f"Skills: {', '.join(skills[:6])}")
    quals = _extract_qualifications(raw_text)
    if quals:
        highlights.append(f"Qualifications: {', '.join(quals[:3])}")

    summary = f"{lead}."
    if highlights:
        summary = f"{summary} {' | '.join(highlights)}"
    elif len(lines) > 1:
        summary = f"{summary} {lines[1][:220]}"

    if len(summary) > 500:
        summary = summary[:497].rstrip() + "..."
    state["resume_summary"] = summary or None
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


def split_manifest_fields_by_source_classification(state: ResumeFormatState) -> ResumeFormatState:
    if state.get("status") in [JobStatus.FAILED, JobStatus.WAITING_FOR_TEMPLATE_SELECTION]:
        return state

    manifest = state.get("manifest") or {"fields": []}
    fields = manifest.get("fields", [])
    buckets: dict[str, list[dict[str, Any]]] = {
        "resume_fact": [],
        "generated": [],
        "input_only": [],
        "recruiter_input": [],
        "ats_input": [],
    }

    for field in fields:
        classification = str(field.get("source_classification", "resume_fact")).strip().lower()
        if classification not in buckets:
            classification = "resume_fact"
        buckets[classification].append(field)

    state["resume_fact_fields"] = buckets["resume_fact"]
    state["generated_fields"] = buckets["generated"]
    state["input_only_fields"] = buckets["input_only"]
    state["recruiter_input_fields"] = buckets["recruiter_input"]
    state["ats_input_fields"] = buckets["ats_input"]

    print(
        f"[FieldSplit] resume_fact={len(buckets['resume_fact'])} generated={len(buckets['generated'])} "
        f"input_only={len(buckets['input_only'])} recruiter_input={len(buckets['recruiter_input'])} "
        f"ats_input={len(buckets['ats_input'])}"
    )
    return state


def extract_resume_fact_fields(state: ResumeFormatState) -> ResumeFormatState:
    if state.get("status") in [JobStatus.FAILED, JobStatus.WAITING_FOR_TEMPLATE_SELECTION]:
        return state

    raw_text = state.get("raw_resume_text") or ""
    fields = state.get("resume_fact_fields") or []

    print(f"[ExtractData] Extracting resume_fact values for {len(fields)} fields...")
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
        extracted = {"field_mappings": {}}
        for field in fields:
            name = str(field.get("name") or "").strip()
            if not name:
                continue

            value = _heuristic_value_for_field(field, raw_text)
            field_type = str(field.get("field_type") or "scalar").lower()
            if _is_empty_mapped_value(value):
                if field_type == "array_object" or field_type == "array":
                    value = []
                else:
                    value = ""

            extracted["field_mappings"][name] = {
                "value": value,
                "status": "mapped" if not _is_empty_mapped_value(value) else "missing",
                "confidence": 0.35 if not _is_empty_mapped_value(value) else 0.0,
                "source": {
                    "page": 1,
                    "section": "Heuristic Resume Fallback",
                    "evidence_text": "Derived from deterministic semantic parsing.",
                },
            }

    field_mappings = extracted.setdefault("field_mappings", {})

    # Retry only missing fields in a focused second pass to reduce omissions.
    missing_fields = [
        f for f in fields
        if _is_empty_mapped_value((field_mappings.get(f.get("name", ""), {}) or {}).get("value"))
    ]
    if missing_fields:
        print(f"[ExtractData] Retrying focused extraction for {len(missing_fields)} missing resume_fact fields")
        try:
            retry_payload = agentic_core.extract_resume_fields(
                fields=missing_fields,
                resume_text=raw_text,
                use_strong_model=True,
            )
            retry_mappings = (retry_payload or {}).get("field_mappings", {}) or {}
            recovered = 0
            for field in missing_fields:
                name = field.get("name")
                if not name:
                    continue
                retry_entry = retry_mappings.get(name) or {}
                retry_value = retry_entry.get("value")
                if _is_empty_mapped_value(retry_value):
                    continue
                field_mappings[name] = retry_entry
                recovered += 1
            print(f"[ExtractData] Focused retry recovered {recovered} fields")
        except Exception as e:
            print(f"[ExtractData] Focused retry failed ({e})")

    # Deterministic semantic fallback for still-missing key fields.
    heuristic_recovered = _apply_heuristic_resume_fact_fallback(
        fields=fields,
        field_mappings=field_mappings,
        raw_resume_text=raw_text,
    )
    if heuristic_recovered:
        print(f"[ExtractData] Heuristic fallback recovered {heuristic_recovered} fields")

    complex_recovered = _normalize_and_backfill_array_object_fields(
        fields=fields,
        field_mappings=field_mappings,
        raw_resume_text=raw_text,
    )
    if complex_recovered:
        print(f"[ExtractData] Array-object fallback recovered/normalized {complex_recovered} fields")

    state["resume_fact_result"] = extracted
    
    return state


def extract_generated_fields(state: ResumeFormatState) -> ResumeFormatState:
    if state.get("status") in [JobStatus.FAILED, JobStatus.WAITING_FOR_TEMPLATE_SELECTION]:
        return state

    fields = state.get("generated_fields") or []
    if not fields:
        state["generated_result"] = {"field_mappings": {}}
        print("[ExtractData] No generated fields present.")
        return state

    raw_text = state.get("raw_resume_text") or ""
    resume_fact_values = {
        k: v.get("value")
        for k, v in (state.get("resume_fact_result") or {}).get("field_mappings", {}).items()
    }

    print(f"[ExtractData] Generating values for {len(fields)} generated fields...")
    agentic_core = AgenticCore()
    try:
        extracted = agentic_core.generate_resume_fields(
            fields=fields,
            resume_text=raw_text,
            resume_fact_values=resume_fact_values,
            use_strong_model=True,
        )
    except Exception as e:
        print(f"[ExtractData] Generated-field LLM failed ({e}), using empty fallback")
        extracted = {"field_mappings": {}}

    # Backfill generated narrative fields with a deterministic summary when missing.
    generated_mappings = extracted.setdefault("field_mappings", {})
    fallback_summary = (state.get("resume_summary") or "").strip()
    if fallback_summary:
        filled = 0
        for field in fields:
            name = str(field.get("name") or "").strip()
            if not name:
                continue
            existing_value = (generated_mappings.get(name) or {}).get("value")
            if not _is_empty_mapped_value(existing_value):
                continue

            semantic = " ".join(
                str(field.get(k) or "")
                for k in ("name", "display_label", "source_hint", "template_token")
            ).lower()
            if any(term in semantic for term in ("opinion", "summary", "profile", "expert")):
                generated_mappings[name] = {
                    "value": fallback_summary,
                    "status": "mapped",
                    "confidence": 0.35,
                    "source": {
                        "page": 1,
                        "section": "Deterministic Generated Fallback",
                        "evidence_text": "Filled from deterministic resume summary due LLM unavailability.",
                    },
                }
                filled += 1
        if filled:
            print(f"[ExtractData] Deterministic generated fallback filled {filled} fields")

    state["generated_result"] = extracted
    return state


def prepare_input_placeholder_sources(state: ResumeFormatState) -> ResumeFormatState:
    if state.get("status") in [JobStatus.FAILED, JobStatus.WAITING_FOR_TEMPLATE_SELECTION]:
        return state

    print(
        f"[InputPlaceholder] input_only={len(state.get('input_only_fields') or [])} "
        f"recruiter_input={len(state.get('recruiter_input_fields') or [])} "
        f"ats_input={len(state.get('ats_input_fields') or [])}"
    )
    state["recruiter_input_result"] = {"field_mappings": {}}
    state["ats_input_result"] = {"field_mappings": {}}
    return state


def apply_instruction_resume_fields(state: ResumeFormatState) -> ResumeFormatState:
    if state.get("status") in [JobStatus.FAILED, JobStatus.WAITING_FOR_TEMPLATE_SELECTION]:
        return state

    raw_text = state.get("raw_resume_text") or ""
    manifest_fields = (state.get("manifest") or {}).get("fields", []) or []
    resume_fact_mappings = (state.get("resume_fact_result") or {}).setdefault("field_mappings", {})

    applied = _apply_instruction_resume_fields(
        manifest_fields=manifest_fields,
        field_mappings=resume_fact_mappings,
        raw_resume_text=raw_text,
    )
    if applied:
        print(f"[InstructionFields] Applied full resume text to {applied} instruction field(s)")

    return state


def merge_extracted_sources(state: ResumeFormatState) -> ResumeFormatState:
    if state.get("status") in [JobStatus.FAILED, JobStatus.WAITING_FOR_TEMPLATE_SELECTION]:
        return state

    merged: dict[str, Any] = {"field_mappings": {}}
    for source_name in ("resume_fact_result", "generated_result", "recruiter_input_result", "ats_input_result"):
        source_payload = state.get(source_name) or {}
        for key, value in (source_payload.get("field_mappings", {}) or {}).items():
            merged["field_mappings"][key] = value

    state["mapping_result"] = merged
    state["extracted"] = {k: v.get("value") for k, v in merged["field_mappings"].items()}
    return state


def build_render_payload(state: ResumeFormatState) -> ResumeFormatState:
    if state.get("status") in [JobStatus.FAILED, JobStatus.WAITING_FOR_TEMPLATE_SELECTION]:
        return state
    manifest = state.get("manifest") or {"fields": []}
    mapping_result = state.get("mapping_result") or {}
    recruiter_input = {k: v.get("value") for k, v in (state.get("recruiter_input_result") or {}).get("field_mappings", {}).items()}
    ats_input = {k: v.get("value") for k, v in (state.get("ats_input_result") or {}).get("field_mappings", {}).items()}
    payload = build_filled_template_payload(manifest, mapping_result, recruiter_input=recruiter_input, ats_input=ats_input)
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
    graph.add_node("create_resume_summary", create_resume_summary)
    graph.add_node("resolve_or_suggest_template", resolve_or_suggest_template)
    graph.add_node("load_template_manifest", load_template_manifest)
    graph.add_node("split_manifest_fields_by_source_classification", split_manifest_fields_by_source_classification)
    graph.add_node("extract_resume_fact_fields", extract_resume_fact_fields)
    graph.add_node("extract_generated_fields", extract_generated_fields)
    graph.add_node("prepare_input_placeholder_sources", prepare_input_placeholder_sources)
    graph.add_node("apply_instruction_resume_fields", apply_instruction_resume_fields)
    graph.add_node("merge_extracted_sources", merge_extracted_sources)
    graph.add_node("build_render_payload", build_render_payload)
    graph.add_node("render_resume", render_resume)

    graph.set_entry_point("load_resume_input")
    graph.add_edge("load_resume_input", "create_resume_summary")
    graph.add_edge("create_resume_summary", "resolve_or_suggest_template")
    graph.add_conditional_edges(
        "resolve_or_suggest_template",
        route_after_suggest,
        {"load_template_manifest": "load_template_manifest", END: END},
    )
    graph.add_edge("load_template_manifest", "split_manifest_fields_by_source_classification")
    graph.add_edge("split_manifest_fields_by_source_classification", "extract_resume_fact_fields")
    graph.add_edge("extract_resume_fact_fields", "extract_generated_fields")
    graph.add_edge("extract_generated_fields", "prepare_input_placeholder_sources")
    graph.add_edge("prepare_input_placeholder_sources", "apply_instruction_resume_fields")
    graph.add_edge("apply_instruction_resume_fields", "merge_extracted_sources")
    graph.add_edge("merge_extracted_sources", "build_render_payload")
    graph.add_edge("build_render_payload", "render_resume")
    graph.add_edge("render_resume", END)
    return graph.compile()


def run_resume_format(
    job_id: str,
    template_id: str | None,
    resume_text: str | None = None,
    resume_object_key: str | None = None,
) -> GraphResult:
    from src.shared.repository import active_job_id
    token = active_job_id.set(job_id)
    try:
        app = build_resume_format_graph()
        result = app.invoke(
            {
                "job_id": job_id,
                "template_id": template_id,
                "resume_text": resume_text,
                "resume_object_key": resume_object_key,
                "raw_resume_text": None,
                "resume_summary": None,
                "suggested_templates": [],
                "manifest": None,
                "resume_fact_fields": [],
                "generated_fields": [],
                "input_only_fields": [],
                "recruiter_input_fields": [],
                "ats_input_fields": [],
                "resume_fact_result": {},
                "generated_result": {},
                "recruiter_input_result": {},
                "ats_input_result": {},
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
                "resume_summary": result.get("resume_summary"),
                "suggested_templates": result.get("suggested_templates", []),
                "extracted": result.get("extracted", {}),
                "filled_manifest": result.get("filled_manifest"),
                "rendered_bytes": result.get("rendered_bytes"),
            },
            error=result.get("error"),
        )
    finally:
        active_job_id.reset(token)
