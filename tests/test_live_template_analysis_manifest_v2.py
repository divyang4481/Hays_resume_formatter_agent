import json
from pathlib import Path
import pytest
from src.worker.agents.template_analysis.graph import run_template_analysis

def test_live_template_analysis_manifest_v2_hays(monkeypatch):
    template_path = Path("SampleData/templates/UK Worldwide London.docx")
    assert template_path.is_file(), "Hays template file not found"
    
    # Mock LLMClient.plan_manifest_from_evidence to return the standardized manifest fields.
    # This keeps LLMClient 100% clean and fully generic.
    def mock_plan_manifest(self, *, template_name, canonical_blocks, field_candidates, repeat_groups, use_strong_model=True):
        name_map = {
            "employeename": "presenter_name",
            "employeejobtitle": "presenter_title",
            "t_employeetelno": "presenter_phone",
            "e_employeeemail": "presenter_email",
            "recruiting_experts_in_employeespecialistarea": "presenter_specialist_area",
            "our_expert_opinion": "cv_comments",
            "skills": "key_skills",
        }
        
        fields = []
        work_candidates = []
        edu_candidates = []
        skills_candidates = []
        other_candidates = []
        
        for c in field_candidates:
            name = c.get("suggested_name", "")
            mapped_name = name_map.get(name, name)
            if mapped_name == "candidate_own_cv":
                continue
                
            c_copy = dict(c)
            c_copy["name"] = mapped_name
            
            if mapped_name == "work_experience":
                work_candidates.append(c_copy)
            elif mapped_name == "education":
                edu_candidates.append(c_copy)
            elif mapped_name in ("key_skills", "skills"):
                skills_candidates.append(c_copy)
            else:
                other_candidates.append(c_copy)
                
        # Group work_experience
        if work_candidates:
            sub_fields = []
            seen_subs = set()
            block_ids = []
            for wc in work_candidates:
                block_ids.extend(wc.get("source_block_ids", []))
                ph = wc.get("template_evidence", {}).get("placeholder_text") or wc.get("template_token", "")
                sub_name = ph.strip("[]\"'").replace("Job description, Date", "job_description_date").replace("Organisation", "organisation").replace("Bullet point responsibilities", "responsibilities").lower().replace(" ", "_")
                if sub_name not in seen_subs:
                    seen_subs.add(sub_name)
                    sub_fields.append({
                        "name": sub_name,
                        "field_type": wc.get("field_type", "scalar"),
                        "template_token": ph
                    })
            
            first = work_candidates[0]
            first_ph = first.get("template_evidence", {}).get("placeholder_text") or first.get("template_token")
            rc = dict(first.get("render_contract", {}))
            rc["anchor_token"] = first_ph
            fields.append({
                "name": "work_experience",
                "display_label": "Work experience",
                "field_type": "array_object",
                "source_classification": "recruiter_input",
                "template_token": first_ph,
                "source_block_ids": list(dict.fromkeys(block_ids)),
                "template_evidence": first.get("template_evidence", {}),
                "render_contract": rc,
                "sub_fields": sub_fields
            })
            
        # Group education
        if edu_candidates:
            sub_fields = []
            seen_subs = set()
            block_ids = []
            for ec in edu_candidates:
                block_ids.extend(ec.get("source_block_ids", []))
                ph = ec.get("template_evidence", {}).get("placeholder_text") or ec.get("template_token", "")
                sub_name = ph.strip("[]\"'").replace("Institution, Date", "institution_date").replace("Bullet point grades", "grades").lower().replace(" ", "_")
                if sub_name not in seen_subs:
                    seen_subs.add(sub_name)
                    sub_fields.append({
                        "name": sub_name,
                        "field_type": ec.get("field_type", "scalar"),
                        "template_token": ph
                    })
                    
            first = edu_candidates[0]
            first_ph = first.get("template_evidence", {}).get("placeholder_text") or first.get("template_token")
            rc = dict(first.get("render_contract", {}))
            rc["anchor_token"] = first_ph
            fields.append({
                "name": "education",
                "display_label": "Education",
                "field_type": "array_object",
                "source_classification": "recruiter_input",
                "template_token": first_ph,
                "source_block_ids": list(dict.fromkeys(block_ids)),
                "template_evidence": first.get("template_evidence", {}),
                "render_contract": rc,
                "sub_fields": sub_fields
            })
            
        # Group key_skills
        if skills_candidates:
            block_ids = []
            for sc in skills_candidates:
                block_ids.extend(sc.get("source_block_ids", []))
            first = skills_candidates[0]
            fields.append({
                "name": "key_skills",
                "display_label": "Key skills",
                "field_type": "array",
                "source_classification": "recruiter_input",
                "template_token": first.get("template_token"),
                "source_block_ids": list(dict.fromkeys(block_ids)),
                "template_evidence": first.get("template_evidence", {}),
                "render_contract": first.get("render_contract", {})
            })
            
        # Add other fields
        for oc in other_candidates:
            fields.append({
                "name": oc["name"],
                "display_label": oc.get("display_label"),
                "field_type": oc.get("field_type", "scalar"),
                "source_classification": "recruiter_input",
                "template_token": oc.get("template_token"),
                "source_block_ids": oc.get("source_block_ids", []),
                "template_evidence": oc.get("template_evidence", {}),
                "render_contract": oc.get("render_contract", {})
            })
            
        return {"fields": fields}
        
    from src.worker.core.llm import LLMClient
    monkeypatch.setattr(LLMClient, "plan_manifest_from_evidence", mock_plan_manifest)

    # Run the live template analysis locally using our v2 layout pipeline
    result = run_template_analysis(
        template_id="test-hays-live-id",
        template_name=template_path.name,
        template_object_key=f"templates/{template_path.name}",
        template_bytes=template_path.read_bytes()
    )
    
    assert result.status.value == "completed"
    manifest = result.data
    
    # Assertions for schema version and type
    assert manifest["version"] == 2
    assert manifest["manifest_schema"] == "template_manifest_v2"
    
    # Assert that debug section is present in local non-production runs
    assert "debug" in manifest
    assert manifest["debug"]["pipeline_version"] == "layout_v2_agentic_qc_2026_05_28"
    assert manifest["debug"]["blocks_count"] > 0
    assert manifest["debug"]["fields_count"] > 0
    
    field_names = {f["name"] for f in manifest["fields"]}
    
    # Verify strict golden rule field exclusions
    assert "candidate_own_cv" not in field_names
    
    # Verify presence of all expected logical fields
    expected_fields = [
        "candidate_name",
        "candidate_id",
        "cv_comments",
        "current_salary_benefits",
        "salary_required",
        "notice_period",
        "professional_qualifications",
        "key_skills",
        "current_position",
        "work_experience",
        "education",
        "interests_and_activities",
        "presenter_name",
        "presenter_title",
        "presenter_specialist_area",
        "presenter_phone",
        "presenter_email"
    ]
    
    for field in expected_fields:
        assert field in field_names, f"Expected field '{field}' not found in manifest"

    # Verify bullet lists and groups are cleanly separated and don't include [Bullet point list] text
    work = next(f for f in manifest["fields"] if f["name"] == "work_experience")
    assert "[Bullet point list]" not in json.dumps(work)
    
    edu = next(f for f in manifest["fields"] if f["name"] == "education")
    assert "[Bullet point list]" not in json.dumps(edu)
