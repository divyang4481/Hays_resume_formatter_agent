from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests


def wait_for_job(base_url: str, job_id: str, timeout_seconds: int = 180) -> dict:
    started = time.time()
    while time.time() - started < timeout_seconds:
        response = requests.get(f"{base_url}/jobs/{job_id}", timeout=15)
        response.raise_for_status()
        payload = response.json()
        status = payload.get("status")
        if status in {"completed", "failed", "manual_review"}:
            return payload
        time.sleep(2)
    raise TimeoutError(f"Job {job_id} did not finish within {timeout_seconds} seconds")


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo template extraction and manifest generation")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument(
        "--template",
        default="SampleData/templates/template_1_Software_Engineer.docx",
    )
    args = parser.parse_args()

    template_path = Path(args.template)
    if not template_path.exists():
        raise FileNotFoundError(f"Template file not found: {template_path}")

    with template_path.open("rb") as fp:
        response = requests.post(
            f"{args.base_url}/admin/templates",
            files={"file": (template_path.name, fp, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            timeout=60,
        )
    response.raise_for_status()
    create_payload = response.json()

    template_id = create_payload["template_id"]
    analysis_job_id = create_payload["analysis_job_id"]
    print("Created template:", json.dumps(create_payload, indent=2))

    job_payload = wait_for_job(args.base_url, analysis_job_id)
    print("Analysis job:", json.dumps(job_payload, indent=2))

    manifest_resp = requests.get(f"{args.base_url}/templates/{template_id}/manifest", timeout=30)
    manifest_resp.raise_for_status()
    manifest = manifest_resp.json()

    print("Manifest summary:")
    print(f"template_id={manifest.get('template_id')}")
    print(f"field_count={len(manifest.get('fields', []))}")
    for idx, field in enumerate(manifest.get("fields", [])[:10], start=1):
        print(f"{idx}. name={field.get('name')} type={field.get('field_type')} token={field.get('template_token')}")


if __name__ == "__main__":
    main()
