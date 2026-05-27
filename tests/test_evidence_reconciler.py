from src.worker.agents.template_analysis.extractors.evidence_reconciler import reconcile_template_evidence

def test_reconcile_outputs_canonical_blocks():
    out = reconcile_template_evidence({'blocks':[{'block_id':'ox_b1','raw_token':'[A]','label_text':'A','location':'body','source':'openxml'}]}, {'blocks':[]})
    assert out['canonical_blocks']
