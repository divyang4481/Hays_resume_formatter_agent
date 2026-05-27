from __future__ import annotations

import sys
import os
from pathlib import Path
import json

# Ensure python path has workspace root
sys.path.insert(0, str(Path(__file__).parent.absolute()))

from src.worker.agents.template_analysis.graph import (
    _extract_template_tokens,
    _extract_template_text,
)
from src.worker.core.llm import LLMClient
from src.shared.config import settings


def main():
    templates = [
        "UK Taxation.docx",
        "UK Telecoms.docx",
        "UK Treasury.docx",
        "UK Worldwide London.docx",
        "UK Legal.docx",
        "UK Maintenance.docx",
        "UK Business Support.docx",
    ]

    templates_dir = Path("SampleData/templates")
    llm = LLMClient()

    print("======================================================================")
    print("RUNNING LIVE BEDROCK TEMPLATE ANALYSIS ON HAYS TEMPLATE FILES")
    print("======================================================================\n")

    for template_name in templates:
        template_path = templates_dir / template_name
        if not template_path.exists():
            print(f"Warning: {template_name} not found in {templates_dir}")
            continue

        print(f"Analyzing Template: {template_name}")
        print("-" * 50)

        docx_bytes = template_path.read_bytes()
        tokens = _extract_template_tokens(docx_bytes)
        text_preview = _extract_template_text(docx_bytes)

        print(f"-> Extracted {len(tokens)} placeholders from file archive.")

        llm_tokens = [{"name": name, "template_token": token} for name, token in tokens]

        try:
            # Direct Bedrock Llama 3 70B foundation call via our LLMClient
            print("-> Requesting Bedrock Llama 3 70b manifest generation...")
            fields = llm.infer_template_fields(
                template_name=template_name,
                tokens=llm_tokens,
                template_text=text_preview,
                use_strong_model=False,  # meta.llama3-70b-instruct-v1:0
            )
            print(f"-> Success! Inferred {len(fields)} manifest fields:")
            print(json.dumps(fields, indent=2))
        except Exception as e:
            print(f"-> Failed during inference: {e}")

        print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    main()
