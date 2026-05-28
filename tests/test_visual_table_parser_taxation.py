import pytest
from src.worker.agents.template_analysis.visual_layout_model import VisualModel, VisualRegion, VisualTable, VisualRow, VisualCell, VisualToken
from src.worker.agents.template_analysis.visual_field_candidate_builder import build_visual_field_candidates
from src.worker.agents.template_analysis.logical_field_grouper import group_logical_fields_from_candidates

def test_label_value_row_detection():
    model = VisualModel()
    table = VisualTable(table_id="t1", table_index=1, region_type="label_value_table")
    row = VisualRow(row_id="r1", table_id="t1", row_index=1, role="label_value_row")

    label_cell = VisualCell(cell_id="c1", table_id="t1", row_index=1, cell_index=0, text="Notice period", role="label_cell")
    value_cell = VisualCell(cell_id="c2", table_id="t1", row_index=1, cell_index=1, text="«NoticePeriod»", role="value_cell")
    token = VisualToken(token_id="tk1", raw_token="MERGEFIELD NoticePeriod", public_token="NoticePeriod", token_kind="mergefield")
    value_cell.tokens.append(token)

    row.cells.extend([label_cell, value_cell])
    table.rows.append(row)
    model.tables.append(table)

    region = VisualRegion(region_id="r1", region_type="label_value_table", heading="Header", tables=["t1"])
    model.regions.append(region)

    candidates = build_visual_field_candidates(model)
    fields = group_logical_fields_from_candidates(candidates, {})

    fields_by_name = {f["name"]: f for f in fields}
    assert "notice_period" in fields_by_name
    assert fields_by_name["notice_period"]["template_evidence"]["region_type"] == "label_value_table"
    assert fields_by_name["notice_period"]["template_evidence"]["label_text"] == "Notice period"
