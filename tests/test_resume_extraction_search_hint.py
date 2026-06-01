from src.worker.core.llm import LLMClient


def test_enrich_fields_for_resume_extraction_adds_search_hint_without_overwriting_existing():
    client = LLMClient.__new__(LLMClient)

    fields = [
        {
            "name": "professional_qualifications",
            "display_label": "Professional qualifications",
            "source_hint": "Use certification or accreditation entries",
            "template_token": "CheckType",
            "template_evidence": {"section_heading": "Professional qualifications"},
            "sub_fields": [{"name": "check_type", "template_token": "CheckType"}],
        },
        {
            "name": "candidate_name",
            "display_label": "Candidate Name",
            "search_hint": "already provided",
        },
    ]

    out = client._enrich_fields_for_resume_extraction(fields)

    assert len(out) == 2
    assert out[0]["search_hint"]
    assert "Professional qualifications" in out[0]["search_hint"]
    assert "CheckType" in out[0]["search_hint"]
    assert "Certification" in out[0]["search_hint"]
    assert out[1]["search_hint"] == "already provided"
