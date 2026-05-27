import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import List, Dict


def _clean_field_name(raw: str) -> str:
    """Strip surrounding wrappers and normalize to snake_case."""
    text = raw.strip().strip('"').strip("'").strip('[').strip(']')
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return text or "unknown_field"


def _extract_mergefield_name(instr_text: str) -> str | None:
    match = re.search(r"MERGEFIELD\s+([A-Za-z0-9_:]+)", instr_text, re.IGNORECASE)
    return match.group(1) if match else None


def _extract_macro_placeholder(instr_text: str) -> str | None:
    # Supports both [Type text] and "Use bullets if required"
    br = re.search(r"\[([^\]]+)\]", instr_text)
    if br:
        return br.group(1).strip()
    qt = re.search(r'"([^"]+)"', instr_text)
    if qt:
        return qt.group(1).strip()
    return None



def extract_fields_from_docx(docx_path: Path) -> List[Dict]:
    if not docx_path.is_file():
        raise FileNotFoundError(f"DOCX not found: {docx_path}")

    with zipfile.ZipFile(docx_path, "r") as zip_ref:
        xml_bytes = zip_ref.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

    fields: List[Dict] = []
    counts_by_base_name: dict[str, int] = {}
    current_heading = ""

    for p in root.findall('.//w:p', ns):
        texts = [(t.text or "") for t in p.findall('.//w:t', ns)]
        paragraph_text = "".join(texts).strip()
        p_style = p.find('./w:pPr/w:pStyle', ns)
        style_val = (p_style.attrib.get(f"{{{ns['w']}}}val", "") if p_style is not None else "").lower()
        is_bullet = p.find('.//w:numPr', ns) is not None

        if paragraph_text and ("heading" in style_val or "title" in style_val or paragraph_text.isupper()):
            current_heading = paragraph_text


        # Gather likely labels from current paragraph text
        source_hint = paragraph_text or current_heading

        # fldSimple MERGEFIELD
        for fld in p.findall('.//w:fldSimple', ns):
            instr_text = fld.attrib.get(f"{{{ns['w']}}}instr", "")
            mf = _extract_mergefield_name(instr_text)
            if not mf:
                continue
            base_name = _clean_field_name(mf)
            fields.append({
                "name": base_name,
                "type": "scalar",
                "required": True,
                "source_hint": source_hint,
                "token": f"MERGEFIELD {mf}",
                "context": {"heading": current_heading, "style": style_val, "is_bullet": is_bullet},
            })

        # instrText MERGEFIELD / MACROBUTTON
        for instr in p.findall('.//w:instrText', ns):
            instr_text = (instr.text or "").strip()
            if not instr_text:
                continue
            mf = _extract_mergefield_name(instr_text)
            if mf:
                base_name = _clean_field_name(mf)
                fields.append({
                    "name": base_name,
                    "type": "scalar",
                    "required": True,
                    "source_hint": source_hint,
                    "token": f"MERGEFIELD {mf}",
                    "context": {"heading": current_heading, "style": style_val, "is_bullet": is_bullet},
                })
                continue

            if "MACROBUTTON" in instr_text.upper():
                raw_placeholder = _extract_macro_placeholder(instr_text)
                if not raw_placeholder:
                    continue
                base_name = _clean_field_name(raw_placeholder)

                # Disambiguate generic placeholders by semantic context
                if base_name in {"type_text", "type_text_"}:
                    context_seed = source_hint or current_heading or "field"
                    base_name = _clean_field_name(context_seed)

                if is_bullet:
                    token_name = f"{base_name}_item"
                else:
                    token_name = base_name

                counts_by_base_name[token_name] = counts_by_base_name.get(token_name, 0) + 1
                occurrence = counts_by_base_name[token_name]
                final_name = token_name if occurrence == 1 else f"{token_name}_{occurrence}"

                inferred_type = "array" if is_bullet else "scalar"
                fields.append({
                    "name": final_name,
                    "type": inferred_type,
                    "required": True,
                    "source_hint": source_hint,
                    "token": instr_text,
                    "context": {"heading": current_heading, "style": style_val, "is_bullet": is_bullet},
                })

    return fields


def build_manifest(template_id: str, fields: List[Dict]) -> Dict:
    return {
        "template_id": template_id,
        "manifest_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "fields": fields,
    }
