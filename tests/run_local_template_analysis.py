from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.worker.agents.template_analysis.graph import run_template_analysis


def print_manifest_summary(manifest: dict) -> None:
    fields = manifest.get("fields", [])
    print("=" * 80)
    print("LOCAL TEMPLATE ANALYSIS")
    print("=" * 80)
    print(f"template_id      : {manifest.get('template_id')}")
    print(f"manifest_id      : {manifest.get('manifest_id')}")
    print(f"manifest_version : {manifest.get('version')}")
    print(f"manifest_schema  : {manifest.get('manifest_schema')}")
    print(f"fields_count     : {len(fields)}")
    print("-" * 80)
    for index, field in enumerate(fields, start=1):
        render_contract = field.get("render_contract") or {}
        evidence = field.get("template_evidence") or {}
        print(f"[{index}] {field.get('name')}")
        print(f"  display_label        : {field.get('display_label')}")
        print(f"  field_type           : {field.get('field_type')}")
        print(f"  source_classification: {field.get('source_classification')}")
        print(f"  template_token       : {field.get('template_token')}")
        print(f"  render_strategy      : {render_contract.get('render_strategy')}")
        print(f"  section_heading      : {evidence.get('section_heading')}")
        sub_fields = field.get("sub_fields") or []
        if sub_fields:
            print("  sub_fields:")
            for sub_field in sub_fields:
                print(
                    f"    - {sub_field.get('name')} "
                    f"({sub_field.get('field_type')}) token={sub_field.get('template_token')}"
                )
        print("-" * 80)



def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run local template analysis and print the manifest for a DOCX template"
    )
    parser.add_argument(
        "--template",
        nargs="+",
        required=True,
        help="Path to the local .docx template file (quotes optional, spaces allowed)",
    )
    parser.add_argument(
        "--save-manifest",
        metavar="FILE",
        default=None,
        help="Optional path to save the raw manifest JSON",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Print only the field summary instead of the full JSON",
    )
    parser.add_argument(
        "--skip-llm-planner",
        action="store_true",
        help="Disable the LLM manifest planner and use deterministic grouping only",
    )
    args = parser.parse_args()

    template_path = Path(" ".join(args.template))
    if not template_path.exists():
        raise SystemExit(f"Template file not found: {template_path}")
    if template_path.suffix.lower() != ".docx":
        raise SystemExit("Only .docx templates are supported")

    if args.skip_llm_planner:
        os.environ["TEMPLATE_ANALYSIS_USE_LLM_PLANNER"] = "0"

    result = run_template_analysis(
        template_id=f"local-{template_path.stem.lower().replace(' ', '-')}",
        template_name=template_path.name,
        template_object_key="",
        template_bytes=template_path.read_bytes(),
    )

    manifest = result.data
    print_manifest_summary(manifest)

    if not args.summary_only:
        print("\n[Full Manifest JSON]")
        print(json.dumps(manifest, indent=2, ensure_ascii=False))

    if args.save_manifest:
        output_path = Path(args.save_manifest)
        output_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nManifest JSON saved to: {output_path.resolve()}")


if __name__ == "__main__":
    main()
