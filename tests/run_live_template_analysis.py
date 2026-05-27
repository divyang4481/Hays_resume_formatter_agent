"""
run_live_template_analysis.py
------------------------------
Upload a DOCX template file to the API, wait for analysis to complete,
and print the generated field manifest.

Usage:
    python tests/run_live_template_analysis.py --template SampleData/templates/UK\ Treasury.docx
    python tests/run_live_template_analysis.py --template SampleData/templates/UK\ Treasury.docx --host http://localhost:8000
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path


def upload_template(template_path: Path, host: str) -> tuple[str, str]:
    """Upload a DOCX template file and return (template_id, analysis_job_id)."""
    import urllib.request

    url = f"{host}/admin/templates"
    print(f"\n[Template Upload] Uploading: {template_path.name}")
    print(f"[Template Upload] Endpoint : {url}")

    boundary = "----FormBoundaryHaysAgent"
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="file"; filename="{template_path.name}"\r\n'.encode()
    )
    body.extend(
        b"Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document\r\n\r\n"
    )
    body.extend(template_path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read().decode())
    except Exception as e:
        print(f"[Template Upload] FAILED: {e}")
        sys.exit(1)

    template_id = data["template_id"]
    job_id = data["analysis_job_id"]
    print(f"[Template Upload] SUCCESS")
    print(f"  template_id     : {template_id}")
    print(f"  analysis_job_id : {job_id}")
    return template_id, job_id


def poll_analysis_job(job_id: str, host: str) -> dict:
    """Poll until the template analysis job completes; return the full job record."""
    import urllib.request

    url = f"{host}/jobs/{job_id}"
    print(f"\n[Analysis Polling] Waiting for job to complete...")

    while True:
        try:
            with urllib.request.urlopen(urllib.request.Request(url)) as res:
                job = json.loads(res.read().decode())
        except Exception as e:
            print(f"[Analysis Polling] Poll error: {e}")
            time.sleep(2)
            continue

        status = job["status"]
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"  [{ts}] status: {status}")

        if status == "completed":
            return job
        if status == "failed":
            print(f"[Analysis Polling] Job FAILED: {job.get('error')}")
            sys.exit(1)

        time.sleep(2)


def fetch_manifest(template_id: str, host: str) -> dict:
    """Fetch the full field manifest for a template."""
    import urllib.request

    url = f"{host}/templates/{template_id}/manifest"
    with urllib.request.urlopen(urllib.request.Request(url)) as res:
        return json.loads(res.read().decode())


def print_manifest(manifest: dict) -> None:
    """Pretty-print the manifest fields table."""
    fields = manifest.get("fields", [])
    print(f"\n{'='*70}")
    print(f"MANIFEST  —  {len(fields)} fields")
    print(f"  template_id : {manifest.get('template_id')}")
    print(f"  manifest_id : {manifest.get('manifest_id')}")
    print(f"  created_at  : {manifest.get('created_at')}")
    print(f"{'='*70}")
    print(f"  {'#':<4} {'name':<35} {'type':<16} {'required'}")
    print(f"  {'-'*65}")
    for i, field in enumerate(fields, 1):
        name = field.get("name", "?")
        ftype = field.get("field_type", "scalar")
        required = "YES" if field.get("required") else "no"
        print(f"  {i:<4} {name:<35} {ftype:<16} {required}")
        hint = field.get("source_hint", "")
        if hint:
            print(f"       source_hint : {hint[:80]}")
        token = field.get("template_token", "")
        if token:
            print(f"       token       : {token}")
        sub_fields = field.get("sub_fields", [])
        if sub_fields:
            for sf in sub_fields:
                print(f"         sub  > {sf.get('name','?')} ({sf.get('field_type','scalar')}) — {sf.get('template_token','')}")
    print(f"{'='*70}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload a DOCX template and inspect the generated manifest")
    parser.add_argument(
        "--template",
        nargs="+",
        required=True,
        help="Path to the local .docx template file (quotes optional, spaces allowed)",
    )
    parser.add_argument(
        "--host",
        default="http://localhost:8000",
        help="Base URL of the API (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--save-manifest",
        metavar="FILE",
        default=None,
        help="Optional path to save the raw manifest JSON (e.g. manifest.json)",
    )
    args = parser.parse_args()

    template_path = Path(" ".join(args.template))
    if not template_path.exists():
        print(f"ERROR: Template file not found: {template_path}")
        sys.exit(1)
    if not template_path.suffix.lower() == ".docx":
        print("ERROR: Only .docx templates are supported.")
        sys.exit(1)

    print("=" * 70)
    print("LIVE TEMPLATE ANALYSIS")
    print("=" * 70)

    # 1. Upload
    template_id, job_id = upload_template(template_path, args.host)

    # 2. Poll
    poll_analysis_job(job_id, args.host)
    print(f"\n[Analysis] Completed successfully!")

    # 3. Fetch & print manifest
    manifest = fetch_manifest(template_id, args.host)
    print_manifest(manifest)

    # 4. Optionally save raw JSON
    if args.save_manifest:
        out = Path(args.save_manifest)
        out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[Manifest] Raw JSON saved to: {out.absolute()}")

    print(f"[Done] Use this template_id in run_live_resume_format.py:")
    print(f"       --template-id {template_id}\n")


if __name__ == "__main__":
    main()
