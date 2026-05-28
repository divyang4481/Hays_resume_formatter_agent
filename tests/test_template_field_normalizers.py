from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.worker.agents.template_analysis.logical_field_grouper import canonicalize_field_name, normalize_mergefield_name, split_camel_case


def test_canonicalize_field_name():
    assert canonicalize_field_name("Current salary & benefits") == "current_salary_benefits"
    assert canonicalize_field_name("INTERESTS AND ACTIVITIES") == "interests_and_activities"
    assert canonicalize_field_name("[Bullet point responsibilities]") == "bullet_point_responsibilities"


def test_normalize_mergefield_name():
    assert split_camel_case("CandidateFullName") == ["Candidate", "Full", "Name"]
    assert split_camel_case("EmployeeTelNo") == ["Employee", "Tel", "No"]
    assert normalize_mergefield_name("MERGEFIELD CandidateFullName") == "candidate_name"
    assert normalize_mergefield_name("MERGEFIELD CandidateID") == "candidate_id"
    assert normalize_mergefield_name("MERGEFIELD CandidateTown") == "candidate_town"
    assert normalize_mergefield_name("MERGEFIELD ExpectedSalary") == "expected_salary"
    assert normalize_mergefield_name("MERGEFIELD NoticePeriod") == "notice_period"
    assert normalize_mergefield_name("MERGEFIELD EmployeeName") == "presenter_name"
    assert normalize_mergefield_name("MERGEFIELD EmployeeJobTitle") == "presenter_title"
    assert normalize_mergefield_name("MERGEFIELD EmployeeSpecialistArea") == "presenter_specialist_area"
    assert normalize_mergefield_name("MERGEFIELD EmployeeTelNo") == "presenter_phone"
    assert normalize_mergefield_name("MERGEFIELD EmployeeEmail") == "presenter_email"
