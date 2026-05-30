from __future__ import annotations

from collections import Counter
from typing import Any


def critique_manifest(manifest: dict) -> dict:
    fields = manifest.get("fields", [])
    evidence = manifest.get("layout", {})
    issues: list[dict[str, Any]] = []

    names = [f.get("name") for f in fields if f.get("name")]
    dup_names = [n for n, c in Counter(names).items() if c > 1]
    for n in dup_names:
        issues.append({"severity": "error", "code": "DUPLICATE_FIELD_NAME", "field": n, "message": f"Field appears {Counter(names)[n]} times and should be grouped."})

    for field in fields:
        name = field.get("name") or ""
        token = str(field.get("template_token") or "")
        evidence = field.get("template_evidence") or {}
        render = field.get("render_contract") or {}

        if not field.get("source_block_ids"):
            issues.append({"severity": "error", "code": "MISSING_SOURCE_BLOCK_IDS", "field": name, "message": "Field missing source_block_ids."})
        if not evidence:
            issues.append({"severity": "error", "code": "MISSING_TEMPLATE_EVIDENCE", "field": name, "message": "Field missing template_evidence."})
        if not render:
            issues.append({"severity": "error", "code": "MISSING_RENDER_CONTRACT", "field": name, "message": "Field missing render_contract."})

        if token == "[Type text]" and not (render.get("occurrence_selector") or field.get("occurrence_selector")):
            issues.append({"severity": "error", "code": "MISSING_OCCURRENCE_SELECTOR", "field": name, "message": "Repeated [Type text] fields require occurrence selector."})

        if "[bullet point list]" in token.lower() and field.get("field_type") == "array_object":
            issues.append({"severity": "error", "code": "WRONG_BULLET_TOKEN", "field": name, "message": "array_object fields should not use generic bullet token as anchor."})

        if token == (field.get("display_label") or "") and token:
            issues.append({"severity": "warning", "code": "LABEL_AS_TOKEN", "field": name, "message": "Token appears to be label text rather than a placeholder token."})
        if field.get("suggested_name") and field.get("name") != field.get("suggested_name"):
            issues.append({"severity": "error", "code": "CANONICAL_NAME_NOT_APPLIED", "field": name})
        if name == str(field.get("template_token") or "").strip().lower():
            issues.append({"severity": "warning", "code": "RAW_FIELD_NAME", "field": name})

    # Dynamic repeat evidence check: if section has 2+ unique placeholder tokens repeated >1 across blocks,
    # require an array_object grouped field for that section.
    canonical_blocks = evidence.get("canonical_blocks", [])
    by_section: dict[str, list[dict]] = {}
    for b in canonical_blocks:
        sec = str(b.get("section_heading") or "").strip()
        by_section.setdefault(sec, []).append(b)
    grouped_sections = {str((f.get("template_evidence") or {}).get("section_heading") or "").strip().lower()
                        for f in fields if f.get("field_type") == "array_object"}
    for section, blocks in by_section.items():
        placeholders = [str(b.get("placeholder_text") or "").strip() for b in blocks if b.get("placeholder_text")]
        counts = Counter(placeholders)
        repeated_tokens = [t for t, c in counts.items() if c > 1]
        if len(set(placeholders)) >= 2 and len(repeated_tokens) >= 2 and section.strip().lower() not in grouped_sections:
            issues.append({"severity": "error", "code": "MISSING_REPEAT_SECTION", "section": section})
    # TableStart/TableEnd evidence should map to a grouped array_object section.
    lower_names = {str(f.get("name") or "").strip().lower() for f in fields}
    table_regions: set[str] = set()
    for b in canonical_blocks:
        raw = str(b.get("raw_token") or "")
        if raw.upper().startswith("MERGEFIELD TABLESTART:"):
            table_regions.add(raw.split(":", 1)[1].strip().lower())
    for region in table_regions:
        if region not in lower_names:
            issues.append({"severity": "error", "code": "MISSING_GROUPED_SECTION", "section": region.upper()})

    def _looks_like_list_section(section_name: str, known_sections: set[str]) -> bool:
        s = section_name.strip().lower()
        if not s:
            return False
        if any(k in s for k in ("skill", "qualification", "competenc", "experience", "education", "interest")):
            return True
        return s in known_sections

    list_like_sections = {
        str((f.get("template_evidence") or {}).get("section_heading") or "").strip().lower()
        for f in fields
        if f.get("field_type") in {"array", "array_object"}
    }
    for field in fields:
        name = str(field.get("name") or "")
        ev = field.get("template_evidence") or {}
        section = str(ev.get("section_heading") or "").strip().lower()
        region = str(ev.get("region_type") or "").strip().lower()
        if region == "label_value_table" and _looks_like_list_section(section, list_like_sections):
            issues.append({"severity": "warning", "code": "WRONG_SECTION_CARRYOVER", "field": name, "message": "Label-value field appears incorrectly attached to previous list section."})

        if region == "presenter_footer" and _looks_like_list_section(section, list_like_sections):
            issues.append({"severity": "warning", "code": "PRESENTER_IN_WRONG_SECTION", "field": name, "message": "Presenter field appears under content section."})

        if region == "label_value_table" and (ev.get("row_index") is None or ev.get("cell_index") is None):
            issues.append({"severity": "warning", "code": "LABEL_VALUE_WITHOUT_ROW_CONTEXT", "field": name, "message": "Label-value field is missing row/cell context."})


    # Visual Layout Leak Checks
    lower_names = {str(f.get("name") or "").strip().lower() for f in fields}

    # Check for INSTRUCTION_REGION_AS_FIELD
    for field in fields:
        ev = field.get("template_evidence") or {}
        if ev.get("region_type") == "instruction_region" and ev.get("is_instruction_only"):
            issues.append({"severity": "warning", "code": "INSTRUCTION_REGION_AS_FIELD", "field": field.get("name"), "message": "Instruction region was emitted as a field without content placeholder."})

    # Check for WRONG_HEADING_CARRYOVER
    list_like_sections = {
        str((f.get("template_evidence") or {}).get("section_heading") or "").strip().lower()
        for f in fields
        if f.get("field_type") in {"array", "array_object"}
    }

    def _looks_like_list_section(section_name: str, known_sections: set[str]) -> bool:
        s = section_name.strip().lower()
        if not s:
            return False
        if any(k in s for k in ("skill", "qualification", "competenc", "experience", "education", "interest")):
            return True
        return s in known_sections

    for field in fields:
        name = str(field.get("name") or "")
        ev = field.get("template_evidence") or {}
        section = str(ev.get("section_heading") or "").strip().lower()
        region = str(ev.get("region_type") or "").strip().lower()

        if region == "label_value_table" and _looks_like_list_section(section, list_like_sections):
            issues.append({"severity": "warning", "code": "WRONG_HEADING_CARRYOVER", "field": name, "message": "Label-value table field seems incorrectly attached to previous list heading."})

    # The TABLE_REGION_SCALAR_LEAK rule.
    # If a table region contains CheckType but output exposes only scalar check_type, raise error.
    # Actually, if we group it properly, it will be array_object. So we just need to ensure no `table_start` tokens are left dangling,
    # or if we have a table region evidence but the field is not array_object.
    for field in fields:
        ev = field.get("template_evidence") or {}
        if ev.get("region_type") == "mailmerge_table_region" and field.get("field_type") == "scalar":
             issues.append({"severity": "error", "code": "TABLE_REGION_SCALAR_LEAK", "field": field.get("name"), "message": "Field in mailmerge_table_region exposed as standalone scalar."})

    error_count = sum(1 for i in issues if i.get("severity") == "error")
    warning_count = sum(1 for i in issues if i.get("severity") == "warning")
    score = max(0.0, 1 - 0.08 * error_count - 0.02 * warning_count)
    passed = not any(i["severity"] == "error" for i in issues)
    return {"passed": passed, "score": score, "issues": issues}


def critique_manifest_against_evidence(manifest: dict, evidence: dict) -> dict:
    return critique_manifest(manifest)
