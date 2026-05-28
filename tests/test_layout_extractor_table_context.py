from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))

from pathlib import Path

from src.worker.agents.template_analysis.layout_extractor import extract_layout_blocks_from_docx


def test_layout_extractor_includes_table_context():
    docx = Path("SampleData/templates/UK Taxation.docx").read_bytes()
    layout = extract_layout_blocks_from_docx(docx)
    blocks = layout["blocks"]
    assert any(b.get("table_index") is not None for b in blocks)
    assert any(b.get("row_index") is not None for b in blocks)
    assert any(b.get("region_type") == "label_value_table" for b in blocks)
