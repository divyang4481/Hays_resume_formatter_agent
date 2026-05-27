from __future__ import annotations


def critique_manifest_against_evidence(manifest: dict, evidence: dict) -> dict:
    issues = []
    fields = manifest.get("fields", [])
    blocks = {b["block_id"]: b for b in evidence.get("canonical_blocks", [])}
    names = set()
    for f in fields:
        n = f.get("name")
        if n in names:
            issues.append({"severity": "error", "code": "DUPLICATE_FIELD", "field": n, "message": "duplicate field name"})
        names.add(n)
        token = f.get("template_token", "")
        for bid in f.get("source_block_ids", []):
            b = blocks.get(bid)
            if not b:
                continue
            if token and token not in {b.get("raw_token"), b.get("placeholder_text"), f"MERGEFIELD {b.get('mergefield_name')}"}:
                issues.append({"severity": "error", "code": "FAKE_TOKEN", "field": n, "message": "token not evidenced"})
    score = max(0.0, 1 - (len(issues) * 0.1))
    return {"passed": not issues, "score": score, "issues": issues, "repair_hints": []}
