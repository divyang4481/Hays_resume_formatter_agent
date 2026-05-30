import pytest
from pathlib import Path
from src.worker.agents.template_analysis.visual_layout_model import VisualModel, VisualRegion, VisualTable
from src.worker.agents.template_analysis.visual_debug import build_visual_debug_report

def test_build_visual_debug_report(tmp_path):
    model = VisualModel()
    table = VisualTable(table_id="t1", table_index=1, region_type="label_value_table")
    model.tables.append(table)
    region = VisualRegion(region_id="r1", region_type="label_value_table", tables=["t1"])
    model.regions.append(region)

    report = build_visual_debug_report("Test Template", model, {"fields": []}, tmp_path)

    assert report["visual_regions_count"] == 1
    assert report["visual_tables_count"] == 1
    assert Path(report["visual_model_path"]).exists()
    assert Path(report["visual_debug_html_path"]).exists()
