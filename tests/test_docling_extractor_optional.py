from src.worker.agents.template_analysis.extractors.docling_extractor import extract_docling_layout_evidence

def test_docling_optional():
    out = extract_docling_layout_evidence(b'test', 'x.docx')
    assert out['source'] == 'docling'
    assert 'warnings' in out
