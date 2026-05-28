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

def test_critic_flags_table_region_leak():
    r = critique_manifest_against_evidence(
        {"fields": [{"name": "check_type", "field_type": "scalar", "template_token": "CheckType", "source_block_ids": ["b1"], "template_evidence": {"region_type": "mailmerge_table_region"}, "render_contract": {"render_strategy": "placeholder_replace"}}]},
        {"canonical_blocks": []}
    )
    issues = [i["code"] for i in r["issues"]]
    assert "TABLE_REGION_SCALAR_LEAK" in issues

def test_critic_flags_instruction_region_as_field():
    r = critique_manifest_against_evidence(
        {"fields": [{"name": "own_cv", "field_type": "scalar", "template_token": "Candidate's own CV", "source_block_ids": ["b1"], "template_evidence": {"region_type": "instruction_region", "is_instruction_only": True}, "render_contract": {"render_strategy": "placeholder_replace"}}]},
        {"canonical_blocks": []}
    )
    issues = [i["code"] for i in r["issues"]]
    assert "INSTRUCTION_REGION_AS_FIELD" in issues
