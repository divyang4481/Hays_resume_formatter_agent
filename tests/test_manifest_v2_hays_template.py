from pathlib import Path

from src.worker.agents.template_analysis.layout_extractor import extract_layout_blocks_from_docx


def test_type_text_not_deduped():
    docx = Path('SampleData/templates/UK Worldwide London.docx').read_bytes()
    layout = extract_layout_blocks_from_docx(docx)
    type_text_blocks = [b for b in layout['blocks'] if b.get('placeholder_text') == '[Type text]']
    assert len(type_text_blocks) >= 2
