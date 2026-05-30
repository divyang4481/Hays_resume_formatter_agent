from src.worker.agents.template_analysis.logical_field_grouper import normalize_mergefield_name
from typing import List, Dict, Any
from src.worker.agents.template_analysis.visual_layout_model import VisualModel, VisualRegion

def build_visual_field_candidates(visual_model: VisualModel) -> List[Dict[str, Any]]:
    candidates = []

    # We build dictionary of tables and blocks for easy lookup
    table_map = {t.table_id: t for t in visual_model.tables}
    block_map = {b.block_id: b for b in visual_model.blocks}

    for region in visual_model.regions:
        if region.region_type in ["label_value_table", "profile_label_value_table"]:
            for table_id in region.tables:
                table = table_map.get(table_id)
                if not table:
                    continue

                for r_idx, row in enumerate(table.rows):
                    if row.role == "label_value_row":
                        label_cell = None
                        value_cell = None

                        # Find the cells
                        for c in row.cells:
                            if c.role == "label_cell":
                                label_cell = c
                            if c.role == "value_cell":
                                value_cell = c

                        if not label_cell and len(row.cells) >= 2:
                            label_cell = row.cells[0]
                            value_cell = row.cells[1]

                        if label_cell and value_cell:
                            label_text = label_cell.text.strip()

                            for t_idx, token in enumerate(value_cell.tokens):
                                name = None
                                if token.token_kind == "mergefield":
                                    name = normalize_mergefield_name(token.public_token)
                                elif len(value_cell.tokens) > 1:
                                    name = normalize_mergefield_name(token.public_token)

                                candidate = {
                                    "name": name,  # Will be set by logical grouper or based on label
                                    "display_label": label_text,
                                    "template_token": token.public_token,
                                    "raw_token": token.raw_token,
                                    "source_block_ids": [value_cell.cell_id],
                                    "field_type": "scalar",
                                    "template_evidence": {
                                        "region_type": "label_value_table",
                                        "row_role": "label_value_row",
                                        "label_text": label_text,
                                        "value_text": token.raw_token,
                                        "table_index": table.table_index,
                                        "row_index": r_idx,
                                        "cell_index": value_cell.cell_index,
                                        "section_heading": region.heading or ""
                                    }
                                }
                                candidates.append(candidate)

        elif region.region_type == "mailmerge_table_region":
            for table_id in region.tables:
                table = table_map.get(table_id)
                if not table:
                    continue

                # Each token in the repeat row is a candidate (they will be grouped)
                for r_idx, row in enumerate(table.rows):
                    if row.role == "repeat_region_row":
                        for c_idx, cell in enumerate(row.cells):
                            for token in cell.tokens:
                                if token.token_kind == "mergefield":
                                    candidate = {
                                        "name": None,
                                        "display_label": region.heading or token.public_token,
                                        "template_token": token.public_token,
                                        "raw_token": token.raw_token,
                                        "source_block_ids": [cell.cell_id],
                                        "field_type": "scalar",
                                        "template_evidence": {
                                            "region_type": "mailmerge_table_region",
                                            "row_role": "repeat_region_row",
                                            "table_index": table.table_index,
                                            "row_index": r_idx,
                                            "cell_index": c_idx,
                                            "section_heading": region.heading or ""
                                        }
                                    }
                                    # To help logical_grouper
                                    candidate["raw_token_for_grouping"] = f"MERGEFIELD TABLESTART:{region.region_name}" # fake start so grouper catches it, OR we just let grouper use visual evidence. We will update logical grouper!
                                    # Actually, we can output the field completely formatted as mailmerge table region if we want,
                                    # or we emit candidates and let logical_grouper merge them.
                                    # Let's add the region_name to evidence.
                                    candidate["template_evidence"]["region_name"] = region.region_name
                                    candidates.append(candidate)

        elif region.region_type == "instruction_region" and region.is_instruction_only:
            # Create a placeholder candidate for the LLM to identify the instruction region
            # We don't hardcode candidate_own_cv here. The LLM or fallback logic will use this candidate.
            instruction_text = " ".join([block_map.get(bid).text for bid in region.blocks if block_map.get(bid)])

            candidate = {
                "name": None,
                "display_label": region.heading or "Instruction",
                "template_token": None,
                "raw_token": None,
                "source_block_ids": region.blocks,
                "field_type": "scalar",
                "template_evidence": {
                    "region_type": "instruction_region",
                    "section_heading": region.heading or "",
                    "is_instruction_only": True,
                    "instruction_text": instruction_text
                },
                "render_contract": {
                    "render_strategy": "remove_instruction_text"
                }
            }
            candidates.append(candidate)

        elif region.region_type == "layout_only_table":
            for table_id in region.tables:
                table = table_map.get(table_id)
                if not table:
                    continue
                for r_idx, row in enumerate(table.rows):
                    for c_idx, cell in enumerate(row.cells):
                        for token in cell.tokens:
                            if token.token_kind not in ["table_start", "table_end"]:
                                candidate = {
                                    "name": normalize_mergefield_name(token.public_token),
                                    "display_label": region.heading or token.public_token,
                                    "template_token": token.public_token,
                                    "raw_token": token.raw_token,
                                    "source_block_ids": [cell.cell_id],
                                    "field_type": "scalar",
                                    "template_evidence": {
                                        "region_type": "layout_only_table",
                                        "table_index": table.table_index,
                                        "row_index": r_idx,
                                        "cell_index": c_idx,
                                        "section_heading": region.heading or ""
                                    }
                                }
                                candidates.append(candidate)

        elif region.region_type in ["bullet_list_section", "text_region"]:
            for block_id in region.blocks:
                block = block_map.get(block_id)
                if not block:
                    continue
                for token in block.tokens:
                    if token.token_kind != "table_start" and token.token_kind != "table_end":
                        candidate = {
                            "name": None,
                            "display_label": region.heading or token.public_token,
                            "template_token": token.public_token,
                            "raw_token": token.raw_token,
                            "source_block_ids": [block.block_id],
                            "field_type": "scalar",
                            "template_evidence": {
                                "region_type": region.region_type,
                                "section_heading": region.heading or ""
                            }
                        }
                        candidates.append(candidate)

    return candidates
