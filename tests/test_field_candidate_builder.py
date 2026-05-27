from src.worker.agents.template_analysis.field_candidate_builder import build_field_candidates_from_evidence

def test_builder_creates_candidates():
    c = build_field_candidates_from_evidence({'canonical_blocks':[{'block_id':'b1','raw_token':'[Type text]','label_text':'Current salary & benefits','section_heading':'CANDIDATE PROFILE','occurrence_key':'k'}]})
    assert c[0]['template_token'] == '[Type text]'
