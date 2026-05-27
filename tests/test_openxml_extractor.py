from pathlib import Path
from src.worker.agents.template_analysis.extractors.openxml_extractor import extract_openxml_evidence

def test_openxml_extracts_blocks():
    b = Path('SampleData/templates/UK Worldwide London.docx').read_bytes()
    out = extract_openxml_evidence(b)
    assert out['source'] == 'openxml'
    assert isinstance(out['blocks'], list)
