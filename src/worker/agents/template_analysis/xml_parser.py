import uuid
from datetime import datetime, timezone
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import List, Dict, Any


def _clean_field_name(raw: str) -> str:
    text = raw.strip().strip('"').strip("'").strip('[').strip(']')
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return text or "unknown_field"


def _extract_mergefield_name(instr_text: str) -> str | None:
    match = re.search(r"MERGEFIELD\s+([A-Za-z0-9_:]+)", instr_text, re.IGNORECASE)
    return match.group(1) if match else None


def _extract_macro_placeholder(instr_text: str) -> str | None:
    br = re.search(r"\[([^\]]+)\]", instr_text)
    if br:
        return br.group(1).strip()
    qt = re.search(r'"([^"]+)"', instr_text)
    if qt:
        return qt.group(1).strip()
    return None


def _strip_bracketed(text: str) -> str:
    return re.sub(r"\[[^\]]+\]", " ", text or "").strip()


def _resolve_generic_placeholder_name(raw_placeholder: str, source_hint: str, heading: str) -> str:
    raw = _clean_field_name(raw_placeholder)
    label_seed = _strip_bracketed(source_hint)

    # Prefer nearby label text; fallback to heading.
    candidate = _clean_field_name(label_seed)
    if not candidate or candidate in {"unknown_field", "type_text", "bullet_point_list"}:
        candidate = _clean_field_name(heading)

    # If still too generic, keep placeholder-derived name to avoid template-specific hardcoding.
    if not candidate or candidate in {"unknown_field", "heading", "title"}:
        candidate = raw

    return candidate


def _get_table_context(p: ET.Element, ns: dict, parent_map: dict) -> dict[str, Any]:
    curr = p
    cell = None
    while curr in parent_map:
        curr = parent_map[curr]
        if curr.tag == f"{{{ns['w']}}}tc":
            cell = curr
            break
            
    ctx: dict[str, Any] = {"table_index": None, "row_index": None, "cell_index": None, "label_text": None, "row_text": "", "cell_text": "", "left_cell_text": None, "right_cell_text": None}
    if cell is not None:
        row = parent_map.get(cell)
        if row is not None and row.tag == f"{{{ns['w']}}}tr":
            table = parent_map.get(row)
            cells = row.findall(f"{{{ns['w']}}}tc", ns)
            rows_in_table = table.findall(f"{{{ns['w']}}}tr", ns) if table is not None else []
            if rows_in_table and row in rows_in_table:
                ctx["row_index"] = rows_in_table.index(row)
            try:
                cell_idx = cells.index(cell)
            except ValueError:
                cell_idx = -1
            ctx["cell_index"] = cell_idx if cell_idx >= 0 else None
            cell_texts = [t.text or "" for t in cell.findall(f".//{{{ns['w']}}}t", ns)]
            ctx["cell_text"] = "".join(cell_texts).strip()
            ctx["row_text"] = " ".join("".join((t.text or "") for t in c.findall(f".//{{{ns['w']}}}t", ns)).strip() for c in cells).strip()
            if table is not None and table.tag == f"{{{ns['w']}}}tbl":
                body = parent_map.get(table)
                if body is not None:
                    tables = [c for c in list(body) if c.tag == f"{{{ns['w']}}}tbl"]
                    if table in tables:
                        ctx["table_index"] = tables.index(table)
            if cell_idx > 0:
                left_cell = cells[cell_idx - 1]
                left_texts = [t.text or "" for t in left_cell.findall(f".//{{{ns['w']}}}t", ns)]
                label_text = "".join(left_texts).strip()
                if label_text:
                    ctx["label_text"] = label_text
                    ctx["left_cell_text"] = label_text
            if len(cells) > 1:
                right_text = "".join((t.text or "") for t in cells[1].findall(f".//{{{ns['w']}}}t", ns)).strip()
                ctx["right_cell_text"] = right_text
    return ctx


def extract_fields_from_docx(docx_path: Path) -> List[Dict]:
    if not docx_path.is_file():
        raise FileNotFoundError(f"DOCX not found: {docx_path}")

    with zipfile.ZipFile(docx_path, "r") as zip_ref:
        xml_bytes = zip_ref.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    parent_map = {c: p for p in root.iter() for c in p}

    fields: List[Dict] = []
    counts_by_name: dict[str, int] = {}
    placeholder_occurrence: dict[str, int] = {}
    block_counter = 0
    current_heading = ""

    def next_block(placeholder_text: str, label: str, style: str, is_bullet: bool, table_ctx: dict[str, Any]) -> dict[str, Any]:
        nonlocal block_counter
        block_counter += 1
        placeholder_occurrence[placeholder_text] = placeholder_occurrence.get(placeholder_text, 0) + 1
        return {
            "block_id": f"b{block_counter:03d}",
            "section_heading": current_heading,
            "label_text": label,
            "placeholder_text": placeholder_text,
            "occurrence_index": placeholder_occurrence[placeholder_text],
            "block_type": "bullet_placeholder" if is_bullet else "label_value_row",
            "location": {"style": style, "is_bullet": is_bullet},
            "table_index": table_ctx.get("table_index"),
            "row_index": table_ctx.get("row_index"),
            "cell_index": table_ctx.get("cell_index"),
            "row_text": table_ctx.get("row_text"),
            "cell_text": table_ctx.get("cell_text"),
            "left_cell_text": table_ctx.get("left_cell_text"),
            "right_cell_text": table_ctx.get("right_cell_text"),
        }

    for p in root.findall('.//w:p', ns):
        texts = [(t.text or "") for t in p.findall('.//w:t', ns)]
        paragraph_text = "".join(texts).strip()
        p_style = p.find('./w:pPr/w:pStyle', ns)
        style_val = (p_style.attrib.get(f"{{{ns['w']}}}val", "") if p_style is not None else "").lower()
        is_bullet = p.find('.//w:numPr', ns) is not None

        if paragraph_text and ("heading" in style_val or "title" in style_val or paragraph_text.isupper()):
            current_heading = paragraph_text

        table_ctx = _get_table_context(p, ns, parent_map)
        table_label = table_ctx.get("label_text")
        source_hint = table_label or paragraph_text or current_heading

        for fld in p.findall('.//w:fldSimple', ns):
            instr_text = fld.attrib.get(f"{{{ns['w']}}}instr", "")
            mf = _extract_mergefield_name(instr_text)
            if not mf:
                continue
            base_name = _clean_field_name(mf)
            block = next_block(f"MERGEFIELD {mf}", source_hint, style_val, is_bullet, table_ctx)
            fields.append({"name": base_name, "type": "scalar", "required": True, "source_hint": source_hint,
                          "token": f"MERGEFIELD {mf}", "context": {"heading": current_heading, "style": style_val, "is_bullet": is_bullet},
                          "source_block_ids": [block["block_id"]], "template_evidence": block})

        for instr in p.findall('.//w:instrText', ns):
            instr_text = (instr.text or "").strip()
            if not instr_text:
                continue

            mf = _extract_mergefield_name(instr_text)
            if mf:
                base_name = _clean_field_name(mf)
                block = next_block(f"MERGEFIELD {mf}", source_hint, style_val, is_bullet, table_ctx)
                fields.append({"name": base_name, "type": "scalar", "required": True, "source_hint": source_hint,
                              "token": f"MERGEFIELD {mf}", "context": {"heading": current_heading, "style": style_val, "is_bullet": is_bullet},
                              "source_block_ids": [block["block_id"]], "template_evidence": block})
                continue

            if "MACROBUTTON" not in instr_text.upper():
                continue
            raw_placeholder = _extract_macro_placeholder(instr_text)
            if not raw_placeholder:
                continue

            base_name = _clean_field_name(raw_placeholder)
            if base_name in {"type_text", "type_text_", "bullet_point_list"}:
                base_name = _resolve_generic_placeholder_name(raw_placeholder, source_hint, current_heading)

            token_name = f"{base_name}_item" if is_bullet else base_name
            counts_by_name[token_name] = counts_by_name.get(token_name, 0) + 1
            final_name = token_name if counts_by_name[token_name] == 1 else f"{token_name}_{counts_by_name[token_name]}"
            block = next_block(f"[{raw_placeholder}]", source_hint, style_val, is_bullet, table_ctx)
            fields.append({"name": final_name, "type": "array" if is_bullet else "scalar", "required": True,
                          "source_hint": source_hint, "token": instr_text,
                          "context": {"heading": current_heading, "style": style_val, "is_bullet": is_bullet},
                          "source_block_ids": [block["block_id"]], "template_evidence": block})

    return fields


def build_manifest(template_id: str, fields: List[Dict]) -> Dict:
    return {
        "template_id": template_id,
        "manifest_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "fields": fields,
    }
