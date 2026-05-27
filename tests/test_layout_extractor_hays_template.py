from pathlib import Path

from src.worker.agents.template_analysis.layout_extractor import extract_layout_blocks_from_docx


def test_layout_extractor_returns_blocks():
    docx = Path('SampleData/templates/UK Worldwide London.docx').read_bytes()
    layout = extract_layout_blocks_from_docx(docx)
    assert 'blocks' in layout
    assert isinstance(layout['blocks'], list)
    assert len(layout['blocks']) > 0
