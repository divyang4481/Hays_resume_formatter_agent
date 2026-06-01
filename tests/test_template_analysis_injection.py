from __future__ import annotations

from typing import Any
import pytest

from src.worker.agents.template_analysis import graph
from src.worker.agents.template_analysis.graph import TemplateAnalysisAgent
from src.worker.agents.template_analysis.visual_layout_model import VisualModel
from src.shared.models import JobStatus
from src.shared.storage import SmartTestObjectStore


class MockRepository:
    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self.manifests: dict[str, dict[str, Any]] = {}

    def update_job(self, job_id: str, status: JobStatus, error: str | None = None) -> None:
        self.jobs[job_id] = {"status": status, "error": error}

    def save_manifest(self, template_id: str, manifest: dict[str, Any]) -> None:
        self.manifests[template_id] = manifest


class MockLLMClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.called_plan = False

    def plan_manifest_from_evidence(self, **kwargs: Any) -> dict[str, Any]:
        self.called_plan = True
        return self.response


def test_template_analysis_agent_dependency_injection(monkeypatch) -> None:
    # 1. Prepare minimal valid docx bytes mock (zip archive with empty body element)
    minimal_docx_bytes = b'PK\x03\x04\x14\x00\x00\x00\x00\x00\x13"\xbc\\,+\xb6Sq\x00\x00\x00q\x00\x00\x00\x11\x00\x00\x00word/document.xml<w:document xmlns:w=\'http://schemas.openxmlformats.org/wordprocessingml/2006/main\'><w:body></w:body></w:document>PK\x01\x02\x14\x03\x14\x00\x00\x00\x00\x00\x13"\xbc\\,+\xb6Sq\x00\x00\x00q\x00\x00\x00\x11\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x80\x01\x00\x00\x00\x00word/document.xmlPK\x05\x06\x00\x00\x00\x00\x01\x00\x01\x00?\x00\x00\x00\xa0\x00\x00\x00\x00\x00'

    # Mock low-level extractors to prevent real document layout parser calls
    monkeypatch.setattr(graph, 'extract_openxml_evidence', lambda _: {'blocks': [{'source':'openxml','block_id':'ox_b1','raw_token':'[CandidateFullName]','placeholder_text':'[CandidateFullName]','location':'body'}]})
    monkeypatch.setattr(graph, 'extract_openxml_visual_evidence', lambda _: VisualModel())
    monkeypatch.setattr(graph, 'reconcile_visual_evidence', lambda a, b, c: a)
    monkeypatch.setattr(graph, 'extract_python_docx_visual_evidence', lambda _: None)
    monkeypatch.setattr(graph, 'extract_docling_visual_evidence', lambda *_: None)
    monkeypatch.setattr(graph, 'extract_python_docx_evidence', lambda _: {'blocks': []})
    monkeypatch.setattr(graph, 'extract_docling_layout_evidence', lambda *_: {'blocks': [], 'warnings': []})
    monkeypatch.setattr(graph, 'extract_visual_layout_evidence', lambda *_: {'blocks': [], 'warnings': []})

    # 2. Setup mocked services for injection using SmartTestObjectStore
    mock_store = SmartTestObjectStore()
    mock_store.put_bytes("templates/di_test.docx", minimal_docx_bytes)
    
    mock_repo = MockRepository()
    mock_llm = MockLLMClient({
        "fields": [
            {
                "name": "candidate_name",
                "display_label": "Candidate Name",
                "field_type": "scalar",
                "source_classification": "resume_fact",
                "template_token": "CandidateFullName",
                "source_block_ids": ["ox_b1"],
                "template_evidence": {"section_heading": ""},
                "render_contract": {"render_strategy": "replace_text"},
            }
        ]
    })

    # 3. Instantiate and run TemplateAnalysisAgent
    agent = TemplateAnalysisAgent(
        object_store=mock_store,
        llm_client=mock_llm,
        repo=mock_repo
    )

    result = agent.run_analysis(
        template_id="test-di-template",
        template_name="di_test.docx",
        template_object_key="templates/di_test.docx",
        job_id="test-di-job-123"
    )

    # 4. Assert injection verification
    assert result.status == JobStatus.COMPLETED
    assert mock_llm.called_plan is True

    # Assert DB repository received updates and generated manifest
    assert "test-di-job-123" in mock_repo.jobs
    assert mock_repo.jobs["test-di-job-123"]["status"] == JobStatus.COMPLETED

    assert "test-di-template" in mock_repo.manifests
    manifest = mock_repo.manifests["test-di-template"]
    assert manifest["manifest_schema"] == "template_manifest_v2"
    assert len(manifest["fields"]) == 1
    assert manifest["fields"][0]["name"] == "candidate_name"
