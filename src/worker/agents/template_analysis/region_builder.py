import uuid
from typing import List
from src.worker.agents.template_analysis.visual_layout_model import VisualModel, VisualRegion

def _detect_instruction_intent(text: str) -> bool:
    t = (text or "").lower()
    instruction_phrases = [
        "delete these instructions",
        "delete this instruction",
        "delete this text",
        "paste the",
        "paste your",
        "in this space",
        "before finalising",
        "before finalizing",
        "copy and paste",
        "replace this text",
        "instruction text"
    ]
    return any(phrase in t for phrase in instruction_phrases)

def _is_instruction_heading(heading_text: str, following_elements: list) -> bool:
    h = (heading_text or "").lower()
    heading_keywords = ["instruction", "guideline", "direction", "paste here"]
    if any(kw in h for kw in heading_keywords):
        return True

    instruction_count = 0
    total_checked = 0
    for _, next_type, next_elem in following_elements:
        if next_type in ("table", "heading") or total_checked >= 3:
            break
        if next_type == "block":
            if next_elem.block_type == "heading":
                break
            total_checked += 1
            if _detect_instruction_intent(next_elem.text):
                instruction_count += 1

    return instruction_count > 0

def build_visual_regions(visual_model: VisualModel) -> List[VisualRegion]:
    regions: List[VisualRegion] = []

    current_heading = None
    current_region = None

    def finalize_region():
        nonlocal current_region
        if current_region:
            if current_region.tables or current_region.blocks:
                regions.append(current_region)
            current_region = None

    # Combine blocks and tables to process them in visual order based on order_index
    elements = [(t.order_index, "table", t) for t in visual_model.tables] + \
               [(b.order_index, "block", b) for b in visual_model.blocks]

    elements.sort(key=lambda x: x[0])

    for idx, (_, elem_type, elem) in enumerate(elements):
        if elem_type == "table":
            table = elem
            if table.heading:
                current_heading = table.heading

            # Check if this table acts as an instruction heading/page dynamically
            is_cv_instruction = False
            if len(table.rows) >= 1 and len(table.rows[0].cells) == 1:
                table_text = table.rows[0].cells[0].text.strip()
                if _is_instruction_heading(table_text, elements[idx + 1:]):
                    is_cv_instruction = True

            if is_cv_instruction:
                finalize_region()
                current_heading = table.rows[0].cells[0].text.strip()
                current_region = VisualRegion(
                    region_id=f"r_{uuid.uuid4().hex[:8]}",
                    region_type="instruction_region",
                    heading=current_heading,
                    is_instruction_only=True,
                    render_action="remove_instruction_text",
                    tables=[table.table_id]
                )
                continue

            region_type = table.region_type or "layout_only_table"

            # If it's a mailmerge region, we create a specific region for it
            if region_type == "mailmerge_table_region":
                finalize_region()
                region_name = None
                for row in table.rows:
                    if row.role == "repeat_region_row":
                        for cell in row.cells:
                            for token in cell.tokens:
                                if token.token_kind == "table_start":
                                    region_name = token.region_name
                                    break

                reg = VisualRegion(
                    region_id=f"r_{uuid.uuid4().hex[:8]}",
                    region_type="mailmerge_table_region",
                    heading=current_heading,
                    region_name=region_name,
                    tables=[table.table_id]
                )
                regions.append(reg)
                current_heading = None # stop carryover
                continue


            if region_type in ["label_value_table", "profile_label_value_table"]:
                finalize_region()
                # Clear heading if it's a list heading
                if current_heading and current_heading.lower().strip() in {"key skills", "skills", "professional qualifications"}:
                    current_heading = None

                reg = VisualRegion(
                    region_id=f"r_{uuid.uuid4().hex[:8]}",
                    region_type=region_type,
                    heading=table.heading or current_heading,
                    tables=[table.table_id]
                )
                regions.append(reg)
                if table.heading:
                    current_heading = table.heading
                else:
                    current_heading = None # Don't carry over into the next block if it wasn't a table heading
                continue

            # If we fall through, it's a layout_only_table or something else we didn't handle explicitly
            finalize_region()
            reg = VisualRegion(
                region_id=f"r_{uuid.uuid4().hex[:8]}",
                region_type=region_type,
                heading=current_heading,
                tables=[table.table_id]
            )
            regions.append(reg)
            continue


        elif elem_type == "block":
            block = elem
            if block.block_type == "heading":
                finalize_region()
                current_heading = block.text

                # Check if this block acts as an instruction heading dynamically
                if _is_instruction_heading(current_heading, elements[idx + 1:]):
                    current_region = VisualRegion(
                        region_id=f"r_{uuid.uuid4().hex[:8]}",
                        region_type="instruction_region",
                        heading=current_heading,
                        is_instruction_only=True,
                        render_action="remove_instruction_text",
                        blocks=[block.block_id]
                    )
                    continue

                current_region = VisualRegion(
                    region_id=f"r_{uuid.uuid4().hex[:8]}",
                    region_type="bullet_list_section", # assuming list sections follow headings often
                    heading=current_heading,
                    blocks=[block.block_id]
                )
            else:
                if not current_region:
                    current_region = VisualRegion(
                        region_id=f"r_{uuid.uuid4().hex[:8]}",
                        region_type="text_region",
                        heading=current_heading,
                        blocks=[block.block_id]
                    )
                else:
                    current_region.blocks.append(block.block_id)

    finalize_region()

    visual_model.regions = regions
    return regions
