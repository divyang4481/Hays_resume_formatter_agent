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


def test_split_text_into_logical_paragraphs():
    from src.worker.agents.resume_formatter.injector import split_text_into_logical_paragraphs

    text = (
        "John Doe\n"
        "Software Engineer\n"
        "\n"
        "Summary:\n"
        "A highly motivated engineer with 5 years of experience building scalable applications.\n"
        "Experienced in Python, React, and AWS Cloud services.\n"
        "\n"
        "Experience:\n"
        "- Developed the backend for the main web platform using FastAPI.\n"
        "  Led a team of three developers to successfully launch the project.\n"
        "- Managed CI/CD pipelines.\n"
    )

    paras = split_text_into_logical_paragraphs(text)
    
    # We expect:
    # 1. "John Doe"
    # 2. "Software Engineer"
    # 3. "Summary:"
    # 4. "A highly motivated engineer with 5 years of experience building scalable applications. Experienced in Python, React, and AWS Cloud services."
    # 5. "Experience:"
    # 6. "- Developed the backend for the main web platform using FastAPI. Led a team of three developers to successfully launch the project."
    # 7. "- Managed CI/CD pipelines."
    
    assert len(paras) == 7
    assert paras[0] == "John Doe"
    assert paras[1] == "Software Engineer"
    assert paras[2] == "Summary:"
    assert "scalable applications. Experienced in" in paras[3]
    assert paras[4] == "Experience:"
    assert paras[5] == "- Developed the backend for the main web platform using FastAPI. Led a team of three developers to successfully launch the project."
    assert paras[6] == "- Managed CI/CD pipelines."

