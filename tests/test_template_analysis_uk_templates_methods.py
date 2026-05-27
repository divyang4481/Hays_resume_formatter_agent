from pathlib import Path

import pytest

from src.worker.agents.template_analysis.extractors.openxml_extractor import extract_openxml_evidence
from src.worker.agents.template_analysis.extractors.python_docx_extractor import extract_python_docx_evidence
from src.worker.agents.template_analysis.extractors.evidence_reconciler import reconcile_template_evidence
from src.worker.agents.template_analysis.field_candidate_builder import build_field_candidates_from_evidence
from src.worker.agents.template_analysis.manifest_validator import validate_manifest_fields_against_layout


UK_TEMPLATES = [
    "UK Worldwide London.docx",
    "UK Treasury.docx",
    "UK Telecoms.docx",
]


def _load_template_bytes(name: str) -> bytes:
    return Path("SampleData/templates", name).read_bytes()


@pytest.mark.parametrize("template_name", UK_TEMPLATES)
def test_extractors_return_real_evidence_for_uk_templates(template_name: str):
    docx_bytes = _load_template_bytes(template_name)

    openxml = extract_openxml_evidence(docx_bytes)
    python_docx = extract_python_docx_evidence(docx_bytes)

    assert openxml["source"] == "openxml"
    assert python_docx["source"] == "python_docx"
    assert len(openxml["blocks"]) > 0
    assert len(openxml["blocks"]) + len(python_docx["blocks"]) > 0

    tokens = [b.get("raw_token", "") for b in openxml["blocks"]]
    assert any("MERGEFIELD" in t or t.startswith("[") for t in tokens)


@pytest.mark.parametrize("template_name", UK_TEMPLATES)
def test_reconcile_candidates_validator_roundtrip_for_uk_templates(template_name: str):
    docx_bytes = _load_template_bytes(template_name)
    openxml = extract_openxml_evidence(docx_bytes)
    python_docx = extract_python_docx_evidence(docx_bytes)

    reconciled = reconcile_template_evidence(openxml, python_docx)
    canonical_blocks = reconciled["canonical_blocks"]
    assert len(canonical_blocks) > 0

    candidates = build_field_candidates_from_evidence(reconciled)
    assert len(candidates) > 0

    fields = [
        {
            "name": c["suggested_name"],
            "display_label": c["display_label"],
            "field_type": c["field_type"],
            "source_classification": "recruiter_input",
            "template_token": c["template_token"],
            "source_block_ids": c["source_block_ids"],
            "template_evidence": c["template_evidence"],
            "render_contract": c["render_contract"],
        }
        for c in candidates
    ]

    validated = validate_manifest_fields_against_layout(fields, {"blocks": canonical_blocks})
    assert len(validated) > 0
    for field in validated:
        assert field["source_block_ids"]
        assert field["template_evidence"]
