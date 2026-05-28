from __future__ import annotations

from collections import Counter
from typing import Any


def critique_manifest(manifest: dict) -> dict:
    fields = manifest.get("fields", [])
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

    score = max(0.0, 1 - 0.05 * len(issues))
    passed = not any(i["severity"] == "error" for i in issues)
    return {"passed": passed, "score": score, "issues": issues}


def critique_manifest_against_evidence(manifest: dict, evidence: dict) -> dict:
    return critique_manifest(manifest)
