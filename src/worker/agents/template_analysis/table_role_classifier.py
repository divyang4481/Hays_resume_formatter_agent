from typing import List
from src.worker.agents.template_analysis.visual_layout_model import VisualTable, VisualBlock

def classify_tables(visual_model) -> List[VisualTable]:
    # Modifies tables in place and returns them
    for table in visual_model.tables:
        for row in table.rows:
            # Title row / merged heading row
            if len(row.cells) == 1 and row.cells[0].grid_span > 1:
                text = row.cells[0].text.strip()
                if text.isupper():
                    row.role = "title_row"
                    table.heading = text
                    continue

            # Mailmerge repeat table region
            has_table_start = False
            has_table_end = False
            region_name = None
            for cell in row.cells:
                for token in cell.tokens:
                    if token.token_kind == "table_start":
                        has_table_start = True
                        region_name = token.region_name
                    elif token.token_kind == "table_end":
                        has_table_end = True

            if has_table_start and has_table_end:
                row.role = "repeat_region_row"
                table.region_type = "mailmerge_table_region"
                continue

            # Label-value row
            if len(row.cells) >= 2:
                left_cell = row.cells[0]
                right_cell = row.cells[1]

                left_text = left_cell.text.strip()
                has_tokens_right = len(right_cell.tokens) > 0

                # if left cell is just plain text and right cell has tokens (or bracket placeholders)
                if left_text and has_tokens_right and not left_cell.tokens:
                    row.role = "label_value_row"
                    left_cell.role = "label_cell"
                    right_cell.role = "value_cell"
                    if not table.region_type:
                        table.region_type = "label_value_table"
                    continue

        # Generalize region type if not set but has title row
        if not table.region_type and any(r.role == "title_row" for r in table.rows):
            if any(r.role == "label_value_row" for r in table.rows):
                table.region_type = "profile_label_value_table"

        if not table.region_type:
             if any(r.role == "label_value_row" for r in table.rows):
                 table.region_type = "label_value_table"

    return visual_model.tables
