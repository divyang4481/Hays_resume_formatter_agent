from src.shared.models import JobStatus
from src.worker.agents.resume_formatter import graph


class _FakeAgenticCore:
    def __init__(self) -> None:
        self.calls = []

    def extract_resume_fields(self, *, fields, resume_text, use_strong_model):
        self.calls.append([f.get("name") for f in fields])
        if len(self.calls) == 1:
            return {
                "field_mappings": {
                    "candidate_name": {"value": "Jane Doe", "status": "mapped", "confidence": 0.9, "source": {}},
                    "professional_qualifications": {"value": [], "status": "missing", "confidence": 0.0, "source": {}},
                }
            }

        return {
            "field_mappings": {
                "professional_qualifications": {
                    "value": [{"check_type": "PMP"}],
                    "status": "mapped",
                    "confidence": 0.85,
                    "source": {},
                }
            }
        }


def test_extract_resume_fact_fields_retries_only_missing_fields(monkeypatch):
    fake = _FakeAgenticCore()
    monkeypatch.setattr(graph, "AgenticCore", lambda: fake)

    state = {
        "status": JobStatus.QUEUED,
        "raw_resume_text": "Jane Doe\nPMP",
        "resume_fact_fields": [
            {"name": "candidate_name", "field_type": "scalar"},
            {
                "name": "professional_qualifications",
                "field_type": "array_object",
                "sub_fields": [{"name": "check_type"}],
            },
        ],
        "manifest": {"fields": []},
    }

    out = graph.extract_resume_fact_fields(state)

    assert fake.calls == [["candidate_name", "professional_qualifications"], ["professional_qualifications"]]
    assert out["resume_fact_result"]["field_mappings"]["candidate_name"]["value"] == "Jane Doe"
    assert out["resume_fact_result"]["field_mappings"]["professional_qualifications"]["value"] == [{"check_type": "PMP"}]
