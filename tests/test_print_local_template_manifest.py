from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.worker.agents.template_analysis.graph import run_template_analysis


def test_print_local_template_manifest() -> None:
    template_env = os.environ.get("TEMPLATE_PATH", "").strip()
    assert template_env, "Set TEMPLATE_PATH to the .docx template you want to inspect"

    if os.environ.get("SKIP_LLM_PLANNER", "").strip().lower() in {"1", "true", "yes"}:
        os.environ["TEMPLATE_ANALYSIS_USE_LLM_PLANNER"] = "0"

    template_path = Path(template_env)
    assert template_path.is_file(), f"Template file not found: {template_path}"
    assert template_path.suffix.lower() == ".docx", "Only .docx templates are supported"

    manifest = run_template_analysis(
        template_id=f"print-{template_path.stem.lower().replace(' ', '-')}",
        template_name=template_path.name,
        template_object_key="",
        template_bytes=template_path.read_bytes(),
    ).data

    assert manifest.get("manifest_schema") == "template_manifest_v2"
    assert manifest.get("fields"), "Expected manifest fields"

    print("\n[Template]", template_path)
    print("[Manifest Fields]", len(manifest.get("fields", [])))
    print("[Manifest JSON]")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
