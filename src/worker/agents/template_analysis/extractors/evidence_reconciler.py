from __future__ import annotations


def reconcile_template_evidence(openxml: dict, python_docx: dict, docling: dict | None = None, visual: dict | None = None) -> dict:
    ox = openxml.get("blocks", [])
    pd = python_docx.get("blocks", [])
    canonical = []
    counter = 0
    by_token = {}
    for b in ox + pd:
        token = (b.get("raw_token") or b.get("placeholder_text") or "").strip()
        if not token:
            continue
        by_token.setdefault((token, b.get("label_text", ""), b.get("location", "body")), []).append(b)

    for (token, label, loc), arr in by_token.items():
        for idx, src in enumerate(arr, start=1):
            counter += 1
            canonical.append({
                "block_id": f"b{counter:03d}", "source_refs": [a.get("block_id") for a in arr if a.get("block_id")], "location": loc,
                "page_hint": 1, "section_heading": src.get("section_heading", ""), "label_text": label,
                "placeholder_text": src.get("placeholder_text"), "mergefield_name": src.get("mergefield_name"), "raw_token": token,
                "is_real_replacement_target": True, "container_type": src.get("container_type", "paragraph"), "table_index": src.get("table_index"),
                "row_index": src.get("row_index"), "cell_index": src.get("cell_index"), "is_bullet": src.get("is_bullet", False),
                "occurrence_key": f"{loc}:{label}:{token}:{idx}", "evidence_text": src.get("evidence_text", token), "confidence": 0.95 if src.get("source") == "openxml" else 0.8,
            })
    return {"canonical_blocks": canonical, "repeat_groups": [], "source_diagnostics": {"openxml": len(ox), "python_docx": len(pd)}, "warnings": (docling or {}).get("warnings", []) + (visual or {}).get("warnings", [])}
