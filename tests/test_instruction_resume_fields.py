from src.worker.agents.resume_formatter.graph import _apply_instruction_resume_fields


def test_apply_instruction_resume_fields_forces_full_resume_text():
    manifest_fields = [
        {
            "name": "candidate_own_cv",
            "display_label": "CANDIDATE'S OWN CV",
            "render_contract": {"render_strategy": "remove_instruction_text"},
            "template_evidence": {"region_type": "instruction_region"},
        },
        {
            "name": "candidate_name",
            "display_label": "Candidate name",
            "render_contract": {"render_strategy": "placeholder_replace"},
            "template_evidence": {"region_type": "label_value_table"},
        },
    ]
    mappings = {
        "candidate_own_cv": {
            "value": "Paste candidate CV here",
            "status": "mapped",
            "confidence": 0.5,
            "source": {},
        },
        "candidate_name": {
            "value": "Jane Doe",
            "status": "mapped",
            "confidence": 0.9,
            "source": {},
        },
    }

    applied = _apply_instruction_resume_fields(
        manifest_fields=manifest_fields,
        field_mappings=mappings,
        raw_resume_text="REAL RESUME TEXT",
    )

    assert applied == 1
    assert mappings["candidate_own_cv"]["value"] == "REAL RESUME TEXT"
    assert mappings["candidate_own_cv"]["confidence"] == 1.0
    assert mappings["candidate_name"]["value"] == "Jane Doe"


def test_apply_instruction_resume_fields_noop_when_resume_text_empty():
    manifest_fields = [
        {
            "name": "candidate_own_cv",
            "render_contract": {"render_strategy": "remove_instruction_text"},
        }
    ]
    mappings = {}

    applied = _apply_instruction_resume_fields(
        manifest_fields=manifest_fields,
        field_mappings=mappings,
        raw_resume_text="   ",
    )

    assert applied == 0
    assert mappings == {}
