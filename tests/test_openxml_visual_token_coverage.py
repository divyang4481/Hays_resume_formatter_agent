import pytest
import zipfile
from io import BytesIO
import xml.etree.ElementTree as ET
from pathlib import Path
from src.worker.agents.template_analysis.extractors.openxml_visual_extractor import extract_openxml_visual_evidence, _extract_mergefield_name

def extract_all_mergefields_from_raw_zip(docx_bytes: bytes) -> set[str]:
    zip_ref = zipfile.ZipFile(BytesIO(docx_bytes), "r")
    # We should also check headers and footers to ensure full coverage
    xml_files = [n for n in zip_ref.namelist() if n.startswith("word/") and n.endswith(".xml")]
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

    tokens = set()
    for xml_file in xml_files:
        xml_bytes = zip_ref.read(xml_file)
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError:
            continue

        for fld in root.findall('.//w:fldSimple', ns):
            instr_text = fld.attrib.get(f"{{{ns['w']}}}instr", "")
            mf = _extract_mergefield_name(instr_text)
            if mf:
                tokens.add(mf)

        for instr in root.findall('.//w:instrText', ns):
            instr_text = (instr.text or "").strip()
            mf = _extract_mergefield_name(instr_text)
            if mf:
                tokens.add(mf)

    return tokens

@pytest.mark.parametrize("template_name", ["UK Worldwide London.docx", "UK Taxation.docx", "UK Treasury.docx"])
def test_visual_extractor_does_not_drop_mergefields(template_name):
    filepath = Path("SampleData/templates") / template_name
    if not filepath.exists():
        pytest.skip(f"{filepath} not found")

    docx_bytes = filepath.read_bytes()
    raw_tokens = extract_all_mergefields_from_raw_zip(docx_bytes)

    model = extract_openxml_visual_evidence(docx_bytes)
    visual_tokens = set()
    for table in model.tables:
        for row in table.rows:
            for cell in row.cells:
                for token in cell.tokens:
                    if token.token_kind in ("mergefield", "table_start", "table_end"):
                        visual_tokens.add(token.public_token)

    for block in model.blocks:
        for token in block.tokens:
            if token.token_kind in ("mergefield", "table_start", "table_end"):
                visual_tokens.add(token.public_token)

    missing = raw_tokens - visual_tokens
    assert not missing, f"Visual extractor missed tokens: {missing}"
