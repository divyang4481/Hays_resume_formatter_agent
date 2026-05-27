from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.worker.agents.template_analysis.logical_field_grouper import canonicalize_field_name, normalize_mergefield_name


def test_canonicalize_field_name():
    assert canonicalize_field_name("Current salary & benefits") == "current_salary_benefits"
    assert canonicalize_field_name("INTERESTS AND ACTIVITIES") == "interests_and_activities"
    assert canonicalize_field_name("[Bullet point responsibilities]") == "bullet_point_responsibilities"


def test_normalize_mergefield_name():
    assert normalize_mergefield_name("MERGEFIELD CandidateFullName") == "candidatefullname"
    assert normalize_mergefield_name("MERGEFIELD CandidateID") == "candidateid"
    assert normalize_mergefield_name("MERGEFIELD EmployeeName") == "employeename"
    assert normalize_mergefield_name("MERGEFIELD EmployeeJobTitle") == "employeejobtitle"
    assert normalize_mergefield_name("MERGEFIELD EmployeeSpecialistArea") == "employeespecialistarea"
    assert normalize_mergefield_name("MERGEFIELD EmployeeTelNo") == "employeetelno"
    assert normalize_mergefield_name("MERGEFIELD EmployeeEmail") == "employeeemail"
