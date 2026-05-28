import uuid
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from io import BytesIO
import re
from typing import List, Dict, Any, Tuple
from src.worker.agents.template_analysis.visual_layout_model import VisualToken, VisualCell, VisualRow, VisualTable, VisualBlock, VisualModel

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

def extract_openxml_visual_evidence(docx_bytes: bytes) -> VisualModel:
    zip_ref = zipfile.ZipFile(BytesIO(docx_bytes), "r")
    xml_bytes = zip_ref.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

    model = VisualModel()

    order_idx = 0

    # Iterate through body children to maintain order
    body = root.find('.//w:body', ns)
    if body is None:
        return model

    t_idx = 0
    block_idx = 0

    for child in body:
        if child.tag == f"{{{ns['w']}}}tbl":
            table_elem = child
            table_id = f"tbl_{t_idx:03d}"
            v_table = VisualTable(table_id=table_id, table_index=t_idx)

            row_elements = table_elem.findall('.//w:tr', ns)
            for r_idx, row_elem in enumerate(row_elements):
                row_id = f"{table_id}_r_{r_idx:03d}"
                v_row = VisualRow(row_id=row_id, table_id=table_id, row_index=r_idx)

                cell_elements = row_elem.findall('.//w:tc', ns)
                row_texts = []
                for c_idx, cell_elem in enumerate(cell_elements):
                    cell_id = f"{row_id}_c_{c_idx:03d}"
                    grid_span = 1
                    tcPr = cell_elem.find('./w:tcPr/w:gridSpan', ns)
                    if tcPr is not None:
                        grid_span_val = tcPr.attrib.get(f"{{{ns['w']}}}val")
                        if grid_span_val:
                            grid_span = int(grid_span_val)

                    texts = [t.text or "" for t in cell_elem.findall('.//w:t', ns)]
                    cell_text = "".join(texts).strip()
                    row_texts.append(cell_text)

                    tokens = []
                    for fld in cell_elem.findall('.//w:fldSimple', ns):
                        instr_text = fld.attrib.get(f"{{{ns['w']}}}instr", "")
                        mf = _extract_mergefield_name(instr_text)
                        if mf:
                            tk = "table_start" if mf.lower().startswith("tablestart:") else "table_end" if mf.lower().startswith("tableend:") else "mergefield"
                            reg = mf.split(":", 1)[1] if tk != "mergefield" else None
                            tokens.append(VisualToken(
                                token_id=str(uuid.uuid4()),
                                raw_token=f"MERGEFIELD {mf}",
                                public_token=mf,
                                token_kind=tk,
                                mergefield_name=mf if tk == "mergefield" else None,
                                region_name=reg
                            ))

                    for instr in cell_elem.findall('.//w:instrText', ns):
                        instr_text = (instr.text or "").strip()
                        if not instr_text:
                            continue
                        mf = _extract_mergefield_name(instr_text)
                        if mf:
                            tk = "table_start" if mf.lower().startswith("tablestart:") else "table_end" if mf.lower().startswith("tableend:") else "mergefield"
                            reg = mf.split(":", 1)[1] if tk != "mergefield" else None
                            tokens.append(VisualToken(
                                token_id=str(uuid.uuid4()),
                                raw_token=f"MERGEFIELD {mf}",
                                public_token=mf,
                                token_kind=tk,
                                mergefield_name=mf if tk == "mergefield" else None,
                                region_name=reg
                            ))
                            continue
                        if "MACROBUTTON" in instr_text.upper():
                            raw_placeholder = _extract_macro_placeholder(instr_text)
                            if raw_placeholder:
                                tokens.append(VisualToken(
                                    token_id=str(uuid.uuid4()),
                                    raw_token=instr_text,
                                    public_token=f"[{raw_placeholder}]",
                                    token_kind="macrobutton"
                                ))

                    v_cell = VisualCell(
                        cell_id=cell_id,
                        table_id=table_id,
                        row_index=r_idx,
                        cell_index=c_idx,
                        text=cell_text,
                        tokens=tokens,
                        grid_span=grid_span
                    )
                    v_row.cells.append(v_cell)
                v_row.row_text = " ".join(row_texts).strip()
                v_table.rows.append(v_row)

            # Add table as an item with order_index
            v_table.order_index = order_idx
            order_idx += 1
            model.tables.append(v_table)
            t_idx += 1

        elif child.tag == f"{{{ns['w']}}}p":
            p = child
            texts = [(t.text or "") for t in p.findall('.//w:t', ns)]
            paragraph_text = "".join(texts).strip()

            tokens = []
            for fld in p.findall('.//w:fldSimple', ns):
                instr_text = fld.attrib.get(f"{{{ns['w']}}}instr", "")
                mf = _extract_mergefield_name(instr_text)
                if mf:
                    tk = "table_start" if mf.lower().startswith("tablestart:") else "table_end" if mf.lower().startswith("tableend:") else "mergefield"
                    reg = mf.split(":", 1)[1] if tk != "mergefield" else None
                    tokens.append(VisualToken(
                        token_id=str(uuid.uuid4()),
                        raw_token=f"MERGEFIELD {mf}",
                        public_token=mf,
                        token_kind=tk,
                        mergefield_name=mf if tk == "mergefield" else None,
                        region_name=reg
                    ))

            for instr in p.findall('.//w:instrText', ns):
                instr_text = (instr.text or "").strip()
                if not instr_text:
                    continue
                mf = _extract_mergefield_name(instr_text)
                if mf:
                    tk = "table_start" if mf.lower().startswith("tablestart:") else "table_end" if mf.lower().startswith("tableend:") else "mergefield"
                    reg = mf.split(":", 1)[1] if tk != "mergefield" else None
                    tokens.append(VisualToken(
                        token_id=str(uuid.uuid4()),
                        raw_token=f"MERGEFIELD {mf}",
                        public_token=mf,
                        token_kind=tk,
                        mergefield_name=mf if tk == "mergefield" else None,
                        region_name=reg
                    ))
                    continue
                if "MACROBUTTON" in instr_text.upper():
                    raw_placeholder = _extract_macro_placeholder(instr_text)
                    if raw_placeholder:
                        tokens.append(VisualToken(
                            token_id=str(uuid.uuid4()),
                            raw_token=instr_text,
                            public_token=f"[{raw_placeholder}]",
                            token_kind="macrobutton"
                        ))

            if paragraph_text or tokens:
                p_style = p.find('./w:pPr/w:pStyle', ns)
                style_val = (p_style.attrib.get(f"{{{ns['w']}}}val", "") if p_style is not None else "").lower()
                is_heading = "heading" in style_val or "title" in style_val or (paragraph_text and paragraph_text.isupper()) or (paragraph_text and not tokens and len(paragraph_text.split()) < 6 and not paragraph_text.startswith("•"))

                v_block = VisualBlock(
                    block_id=f"b_{block_idx:03d}",
                    source="openxml",
                    page_index=None,
                    order_index=order_idx,
                    block_type="heading" if is_heading else "paragraph",
                    text=paragraph_text,
                    style_name=style_val,
                    tokens=tokens
                )
                model.blocks.append(v_block)
                order_idx += 1
                block_idx += 1

    return model
