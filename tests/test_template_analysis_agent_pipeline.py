from src.worker.agents.template_analysis import graph
from src.worker.agents.template_analysis.visual_layout_model import VisualModel

def test_pipeline_manifest_v2(monkeypatch):
    monkeypatch.setattr(graph.object_store, 'get_bytes', lambda key: b'PK\x03\x04\x14\x00\x00\x00\x00\x00\x13"\xbc\\,+\xb6Sq\x00\x00\x00q\x00\x00\x00\x11\x00\x00\x00word/document.xml<w:document xmlns:w=\'http://schemas.openxmlformats.org/wordprocessingml/2006/main\'><w:body></w:body></w:document>PK\x01\x02\x14\x03\x14\x00\x00\x00\x00\x00\x13"\xbc\\,+\xb6Sq\x00\x00\x00q\x00\x00\x00\x11\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x80\x01\x00\x00\x00\x00word/document.xmlPK\x05\x06\x00\x00\x00\x00\x01\x00\x01\x00?\x00\x00\x00\xa0\x00\x00\x00\x00\x00')
    monkeypatch.setattr(graph, 'extract_openxml_evidence', lambda _: {'blocks':[{'source':'openxml','block_id':'ox_b1','raw_token':'[Type text]','placeholder_text':'[Type text]','label_text':'Current salary & benefits','location':'body'}]})
    monkeypatch.setattr(graph, 'extract_openxml_visual_evidence', lambda _: VisualModel())
    monkeypatch.setattr(graph, 'reconcile_visual_evidence', lambda a,b,c: a)
    monkeypatch.setattr(graph, 'extract_python_docx_visual_evidence', lambda _: None)
    monkeypatch.setattr(graph, 'extract_docling_visual_evidence', lambda *_: None)
    monkeypatch.setattr(graph, 'extract_python_docx_evidence', lambda _: {'blocks':[]})
    monkeypatch.setattr(graph, 'extract_docling_layout_evidence', lambda *_: {'blocks':[], 'warnings':[]})
    monkeypatch.setattr(graph, 'extract_visual_layout_evidence', lambda *_: {'blocks':[], 'warnings':[]})
    out = graph.run_template_analysis('t1', 'x.docx', 'k').data
    assert out['version'] == 2
    assert out['manifest_schema'] == 'template_manifest_v2'
