from src.worker.agents.template_analysis.manifest_critic import critique_manifest_against_evidence

def test_critic_flags_fake_token():
    r = critique_manifest_against_evidence({'fields':[{'name':'a','template_token':'[B]','source_block_ids':['b1']}]},{'canonical_blocks':[{'block_id':'b1','raw_token':'[A]','placeholder_text':'[A]','mergefield_name':None}]})
    assert not r['passed']
