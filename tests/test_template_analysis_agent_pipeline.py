from src.worker.agents.template_analysis import graph


def test_pipeline_manifest_v2(monkeypatch):
    monkeypatch.setattr(graph.object_store, 'get_bytes', lambda key: b'docx')
    monkeypatch.setattr(graph, 'extract_openxml_evidence', lambda _: {'blocks':[{'source':'openxml','block_id':'ox_b1','raw_token':'[Type text]','placeholder_text':'[Type text]','label_text':'Current salary & benefits','location':'body'}]})
    monkeypatch.setattr(graph, 'extract_python_docx_evidence', lambda _: {'blocks':[]})
    monkeypatch.setattr(graph, 'extract_docling_layout_evidence', lambda *_: {'blocks':[], 'warnings':[]})
    monkeypatch.setattr(graph, 'extract_visual_layout_evidence', lambda *_: {'blocks':[], 'warnings':[]})
    out = graph.run_template_analysis('t1', 'x.docx', 'k').data
    assert out['version'] == 2
    assert out['manifest_schema'] == 'template_manifest_v2'
