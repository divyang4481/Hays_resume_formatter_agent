import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET
from typing import List, Dict

def _clean_field_name(raw: str) -> str:
    """Strip surrounding brackets and whitespace from a raw field token."""
    return raw.strip().strip('"').strip("'").strip('[').strip(']')

def extract_fields_from_docx(docx_path: Path) -> List[Dict]:
    """Extract placeholder fields from a DOCX file using its XML representation.

    The function looks for:
      * MERGEFIELD placeholders (e.g., ``MERGEFIELD CandidateFullName``)
      * MACROBUTTON placeholders that embed a label inside brackets
    It returns a list of manifest‑compatible field dictionaries.
    """
    if not docx_path.is_file():
        raise FileNotFoundError(f"DOCX not found: {docx_path}")

    # Read the main document XML
    with zipfile.ZipFile(docx_path, "r") as zip_ref:
        xml_bytes = zip_ref.read("word/document.xml")
    root = ET.fromstring(xml_bytes)

    # Namespace handling (Word uses a default namespace)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

    fields: List[Dict] = []
    last_label: str = ""
    for p in root.findall('.//w:p', ns):
        # Gather all text runs in the paragraph
        texts = []
        for t in p.findall('.//w:t', ns):
            texts.append(t.text or "")
        paragraph_text = "".join(texts).strip()
        if paragraph_text:
            last_label = paragraph_text  # remember the most recent non‑empty text

        # Look for MERGEFIELDs inside <w:instrText>
        for instr in p.findall('.//w:instrText', ns):
            instr_text = instr.text or ""
            if "MERGEFIELD" in instr_text:
                parts = instr_text.split()
                # MERGEFIELD is usually the second token
                if len(parts) >= 2:
                    raw_name = parts[1]
                    field_name = _clean_field_name(raw_name)
                    fields.append({
                        "name": field_name,
                        "type": "scalar",
                        "required": True,
                        "source_hint": last_label,
                        "token": instr_text.strip(),
                    })
            # MACROBUTTON pattern with bracketed placeholder
            if "MACROBUTTON" in instr_text and "[" in instr_text and "]" in instr_text:
                # Extract the content inside the outermost brackets
                start = instr_text.find("[")
                end = instr_text.rfind("]")
                raw_name = instr_text[start + 1 : end]
                field_name = _clean_field_name(raw_name)
                fields.append({
                    "name": field_name,
                    "type": "scalar",
                    "required": True,
                    "source_hint": last_label,
                    "token": instr_text.strip(),
                })

    return fields

def build_manifest(template_id: str, fields: List[Dict]) -> Dict:
    """Wrap extracted fields into the manifest JSON structure used by the system."""
    return {
        "template_id": template_id,
        "manifest_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "fields": fields,
    }
