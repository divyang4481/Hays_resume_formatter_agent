from src.shared.manifest_models import adapt_v1_field_to_v2

def test_adapt_v1_field_to_v2():
    out = adapt_v1_field_to_v2({"name": "candidate_name", "type": "scalar", "token": "[Name]"})
    assert out["name"] == "candidate_name"
    assert out["field_type"] == "scalar"
    assert "render_contract" in out
