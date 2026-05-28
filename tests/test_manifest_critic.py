from src.worker.agents.template_analysis.manifest_critic import critique_manifest_against_evidence

def test_critic_flags_fake_token():
    r = critique_manifest_against_evidence({'fields':[{'name':'a','template_token':'[B]','source_block_ids':['b1']}]},{'canonical_blocks':[{'block_id':'b1','raw_token':'[A]','placeholder_text':'[A]','mergefield_name':None}]})
    assert not r['passed']


def test_critic_does_not_require_absent_work_and_education():
    r = critique_manifest_against_evidence(
        {"fields": [{"name": "candidate_name", "template_token": "MERGEFIELD CandidateFullName", "source_block_ids": ["b1"], "template_evidence": {"section_heading": "Header"}, "render_contract": {"render_strategy": "placeholder_replace"}}]},
        {"canonical_blocks": [{"block_id": "b1", "raw_token": "MERGEFIELD CandidateFullName", "placeholder_text": "MERGEFIELD CandidateFullName", "section_heading": "Header"}]},
    )
    issue_codes = {i["code"] for i in r["issues"]}
    assert "MISSING_GROUPED_SECTION" not in issue_codes
