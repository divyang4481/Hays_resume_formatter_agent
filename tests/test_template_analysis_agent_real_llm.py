from __future__ import annotations

import json
from pathlib import Path
import pytest

from src.worker.agents.template_analysis.graph import TemplateAnalysisAgent
from src.worker.agentic_core import AgenticCore
from src.shared.models import JobStatus
from src.shared.repository import InMemoryRepository
from src.shared.storage import SmartTestObjectStore


def test_template_analysis_agent_real_llm_di(monkeypatch) -> None:
    # Verify the template exists locally
    template_path = Path("SampleData/templates/UK Taxation.docx")
    assert template_path.is_file(), "Taxation template file not found"

    # 1. Setup smart storage service for testing (smart disk lookup)
    mock_store = SmartTestObjectStore(fallback_dir="SampleData/templates")
    
    # 2. Setup mock database service using InMemoryRepository
    mock_repo = InMemoryRepository()
    import src.shared.repository
    import src.worker.core.llm_call_manager
    monkeypatch.setattr(src.shared.repository, "repo", mock_repo)
    monkeypatch.setattr(src.worker.core.llm_call_manager, "repo", mock_repo)
    
    # Pre-register a job in mock repository
    job = mock_repo.create_job(job_type="template_analysis")
    job_id = job.job_id

    # 3. Setup actual LLM client
    real_llm = AgenticCore()

    # 4. Instantiate TemplateAnalysisAgent with injected dependencies
    agent = TemplateAnalysisAgent(
        object_store=mock_store,
        llm_client=real_llm,
        repo=mock_repo
    )

    # 5. Run analysis (it will download template_bytes using mock_store, run Bedrock real LLM planning, and save to mock_repo)
    result = agent.run_analysis(
        template_id="test-taxation-live-id",
        template_name=template_path.name,
        template_object_key=f"templates/{template_path.name}",
        job_id=job_id
    )

    # 6. Verify result
    assert result.status == JobStatus.COMPLETED
    assert result.data["version"] == 2
    assert result.data["manifest_schema"] == "template_manifest_v2"

    # Verify that mock_repo successfully received manifest and updated job status
    assert job_id in mock_repo.jobs
    assert mock_repo.jobs[job_id].status == JobStatus.COMPLETED

    assert "test-taxation-live-id" in mock_repo.manifests
    manifest = mock_repo.manifests["test-taxation-live-id"]
    assert manifest["version"] == 2
    assert len(manifest["fields"]) > 0

    field_names = {f["name"] for f in manifest["fields"]}
    # Verify we extracted key fields of the UK Taxation template using Bedrock
    expected_fields = ["candidate_name", "candidate_id", "notice_period", "presenter_name"]
    for field in expected_fields:
        assert field in field_names, f"Expected field '{field}' not found in manifest"

    # Verify that the LLM calls made during analysis successfully recorded the job_id
    assert len(mock_repo.llm_calls) > 0
    for call in mock_repo.llm_calls:
        assert call["job_id"] == job_id, f"Expected LLM call to have job_id={job_id}, got {call['job_id']}"

    print(f"Integration test passed! Successfully extracted {len(manifest['fields'])} fields using Bedrock with mock S3, mock DB, and verified job_id association on LLM calls.")

