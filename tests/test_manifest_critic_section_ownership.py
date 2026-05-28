from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.worker.agents.template_analysis.manifest_critic import critique_manifest


def test_critic_flags_wrong_section_carryover_and_presenter_section():
    manifest = {
        "fields": [
            {"name": "notice_period", "template_token": "MERGEFIELD NoticePeriod", "source_block_ids": ["b1"], "template_evidence": {"region_type": "label_value_table", "label_text": "Notice period", "section_heading": "Key skills"}, "render_contract": {"render_strategy": "placeholder_replace"}},
            {"name": "presenter_name", "template_token": "MERGEFIELD EmployeeName", "source_block_ids": ["b2"], "template_evidence": {"section_heading": "Skills", "region_type": "presenter_footer"}, "render_contract": {"render_strategy": "placeholder_replace"}},
        ],
        "layout": {"canonical_blocks": []},
    }
    result = critique_manifest(manifest)
    codes = {i["code"] for i in result["issues"]}
    assert "WRONG_SECTION_CARRYOVER" in codes
    assert "PRESENTER_IN_WRONG_SECTION" in codes
