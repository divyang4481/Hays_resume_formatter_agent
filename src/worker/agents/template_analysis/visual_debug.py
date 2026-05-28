import json
from pathlib import Path
from dataclasses import asdict
from src.worker.agents.template_analysis.visual_layout_model import VisualModel

def build_visual_debug_report(template_name: str, visual_model: VisualModel, manifest: dict, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save JSON artifacts
    model_dict = asdict(visual_model)
    with open(output_dir / "visual_model.json", "w") as f:
        json.dump(model_dict, f, indent=2)

    with open(output_dir / "visual_regions.json", "w") as f:
        json.dump(model_dict.get("regions", []), f, indent=2)

    with open(output_dir / "manifest_v2.json", "w") as f:
        json.dump(manifest, f, indent=2)

    # Build HTML
    html = [f"<html><head><title>Visual Debug - {template_name}</title>"]
    html.append("<style>")
    html.append("body { font-family: sans-serif; margin: 20px; }")
    html.append("table { border-collapse: collapse; margin-bottom: 20px; width: 100%; }")
    html.append("th, td { border: 1px solid #ccc; padding: 8px; text-align: left; vertical-align: top; }")
    html.append(".region { border: 2px solid #0066cc; margin-bottom: 30px; padding: 15px; border-radius: 5px; }")
    html.append(".region-type { background: #e6f2ff; padding: 5px; font-weight: bold; margin-bottom: 10px; display: inline-block; }")
    html.append(".block { margin-bottom: 10px; padding: 10px; background: #f9f9f9; border-left: 4px solid #ccc; }")
    html.append(".field { background: #dff0d8; padding: 5px; margin: 2px; border-radius: 3px; display: inline-block; font-size: 0.9em; }")
    html.append(".token { background: #fcf8e3; padding: 3px; margin: 2px; border-radius: 3px; display: inline-block; border: 1px solid #faebcc; font-size: 0.9em; }")
    html.append("</style></head><body>")

    html.append(f"<h1>Visual Debug: {template_name}</h1>")

    table_map = {t.table_id: t for t in visual_model.tables}
    block_map = {b.block_id: b for b in visual_model.blocks}

    for region in visual_model.regions:
        html.append(f"<div class='region'>")
        html.append(f"<div class='region-type'>{region.region_type}</div>")
        if region.heading:
            html.append(f"<h3>Heading: {region.heading}</h3>")

        for tid in region.tables:
            table = table_map.get(tid)
            if not table: continue
            html.append("<table>")
            for row in table.rows:
                html.append("<tr>")
                for cell in row.cells:
                    colspan = f" colspan='{cell.grid_span}'" if cell.grid_span > 1 else ""
                    html.append(f"<td{colspan}>")
                    if cell.role:
                        html.append(f"<div style='font-size: 0.8em; color: #666; margin-bottom: 5px;'>Role: {cell.role}</div>")
                    html.append(f"<div>{cell.text}</div>")
                    for token in cell.tokens:
                        html.append(f"<div class='token'>{token.raw_token}</div>")
                    html.append("</td>")
                html.append("</tr>")
            html.append("</table>")

        for bid in region.blocks:
            block = block_map.get(bid)
            if not block: continue
            html.append(f"<div class='block'>")
            html.append(f"<div><strong>[{block.block_type}]</strong> {block.text}</div>")
            for token in block.tokens:
                html.append(f"<div class='token'>{token.raw_token}</div>")
            html.append("</div>")

        html.append("</div>")

    html.append("</body></html>")

    with open(output_dir / "visual_debug.html", "w", encoding="utf-8") as f:
        f.write("\n".join(html))


    # Track Tokens Coverage
    raw_visual_tokens = []
    ignored_control_tokens = []
    for t in visual_model.tables:
        for r in t.rows:
            for c in r.cells:
                for token in c.tokens:
                    if token.token_kind in ["table_start", "table_end"]:
                        ignored_control_tokens.append(token.public_token)
                    else:
                        raw_visual_tokens.append(token.public_token)
    for b in visual_model.blocks:
        for token in b.tokens:
            if token.token_kind in ["table_start", "table_end"]:
                ignored_control_tokens.append(token.public_token)
            else:
                raw_visual_tokens.append(token.public_token)

    manifest_fields = manifest.get("fields", [])
    manifest_token_count = sum(1 for f in manifest_fields if f.get("field_type") == "scalar" or f.get("field_type") == "array")
    for f in manifest_fields:
        manifest_token_count += len(f.get("sub_fields", []))

    return {
        "visual_model_path": str(output_dir / "visual_model.json"),
        "visual_debug_html_path": str(output_dir / "visual_debug.html"),
        "visual_regions_count": len(visual_model.regions),
        "visual_tables_count": len(visual_model.tables),
        "raw_visual_tokens_count": len(raw_visual_tokens),
        "manifest_token_count": manifest_token_count,
        "ignored_control_tokens": list(set(ignored_control_tokens))
    }
