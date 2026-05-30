import pytest
from src.worker.agents.template_analysis.logical_field_grouper import group_logical_fields_from_candidates
from src.worker.agents.template_analysis.visual_field_candidate_builder import build_visual_field_candidates
from src.worker.agents.template_analysis.visual_layout_model import VisualModel, VisualRegion, VisualTable, VisualRow, VisualCell, VisualToken

def test_mailmerge_table_region():
    model = VisualModel()
    table = VisualTable(table_id="t1", table_index=1, region_type="mailmerge_table_region")
    row = VisualRow(row_id="r1", table_id="t1", row_index=1, role="repeat_region_row")

    cell = VisualCell(cell_id="c1", table_id="t1", row_index=1, cell_index=1, text="«CheckType»")
    token = VisualToken(token_id="tk1", raw_token="MERGEFIELD CheckType", public_token="CheckType", token_kind="mergefield")
    cell.tokens.append(token)
    row.cells.append(cell)
    table.rows.append(row)
    model.tables.append(table)

    region = VisualRegion(region_id="r1", region_type="mailmerge_table_region", heading="Professional qualifications", region_name="bCheckType", tables=["t1"])
    model.regions.append(region)

    candidates = build_visual_field_candidates(model)
    fields = group_logical_fields_from_candidates(candidates, {})

    assert len(fields) == 1
    f = fields[0]
    assert f["name"] == "professional_qualifications"
    assert f["field_type"] == "array_object"
    assert f["render_contract"]["render_strategy"] == "mailmerge_table_region"
    assert f["render_contract"]["region_name"] == "bCheckType"
    assert len(f["sub_fields"]) == 1
    assert f["sub_fields"][0]["name"] == "check_type"
