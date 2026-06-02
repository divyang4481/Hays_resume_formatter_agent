"""
run_live_resume_format.py
--------------------------
Format a resume against an existing template (by template_id from the database),
download the resulting DOCX, and print the full filled manifest.

Usage:
    python tests/run_live_resume_format.py \
        --template-id 49dbdc43-4df9-4765-af3c-2a103ffeb200 \
        --resume SampleData/orginal_data/Divyang_Panchasara-2026.pdf

    python tests/run_live_resume_format.py \
        --template-id <id> \
        --resume <path-to-resume> \
        --output my_formatted_resume.docx \
        --host http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Step helpers
# ---------------------------------------------------------------------------


def submit_format_job(template_id: str, resume_path: Path, host: str) -> str:
    """Upload the resume file + template_id and return the format job_id."""
    import urllib.request

    url = f"{host}/format"
    print(f"\n[Format Submit] Uploading resume  : {resume_path.name}")
    print(f"[Format Submit] Template ID       : {template_id}")
    print(f"[Format Submit] Endpoint          : {url}")

    ext = resume_path.suffix.lower()
    mime_map = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".txt": "text/plain",
    }
    mime = mime_map.get(ext, "application/octet-stream")

    boundary = "----FormBoundaryHaysAgent"
    body = bytearray()

    # --- resume file field ---
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="file"; filename="{resume_path.name}"\r\n'.encode()
    )
    body.extend(f"Content-Type: {mime}\r\n\r\n".encode())
    body.extend(resume_path.read_bytes())
    body.extend(b"\r\n")

    # --- template_id field ---
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="template_id"\r\n\r\n')
    body.extend(template_id.encode())
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
        print(f"[Format Submit] FAILED: {e}")
        sys.exit(1)

    job_id = data["job_id"]
    print(f"[Format Submit] Queued — job_id: {job_id}")
    return job_id


def poll_format_job(job_id: str, host: str) -> dict:
    """Poll until the format job completes; return the full job record."""
    import urllib.request

    url = f"{host}/api/jobs/{job_id}"
    print(f"\n[Polling] Waiting for format job to complete...")

    while True:
        try:
            with urllib.request.urlopen(urllib.request.Request(url)) as res:
                job = json.loads(res.read().decode())
        except Exception as e:
            print(f"[Polling] Poll error: {e}")
            time.sleep(3)
            continue

        status = job["status"]
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"  [{ts}] status: {status}")

        if status == "completed":
            return job
        if status == "failed":
            print(f"[Polling] Job FAILED: {job.get('error')}")
            sys.exit(1)

        time.sleep(3)


def download_docx(job_id: str, output_path: Path, host: str) -> None:
    """Download the completed formatted DOCX."""
    import urllib.request

    url = f"{host}/jobs/{job_id}/download"
    print(f"\n[Download] Fetching from: {url}")
    try:
        with urllib.request.urlopen(urllib.request.Request(url)) as res:
            output_path.write_bytes(res.read())
        print(f"[Download] Saved to: {output_path.absolute()}")
    except Exception as e:
        print(f"[Download] FAILED: {e}")
        sys.exit(1)


def print_filled_manifest(job: dict) -> None:
    """Print the stored filled manifest from the job record."""
    extracted_data = job.get("extracted_data")

    print(f"\n{'='*70}")
    print("FILLED MANIFEST")
    print(f"{'='*70}")

    if not extracted_data:
        print("  (No extracted_data stored on this job)")
        return

    # Handle both rich filled_manifest structure and plain flat dict
    filled_values = extracted_data.get("filled_values", extracted_data)
    fields_meta: dict = {f["name"]: f for f in extracted_data.get("fields", [])}
    filled_at = extracted_data.get("filled_at", "")
    if filled_at:
        print(f"  Filled at : {filled_at}")
    print(f"  Fields    : {len(filled_values)}")
    print()

    ok_fields: list[str] = []
    null_required: list[str] = []
    null_optional: list[str] = []

    for fname, fval in filled_values.items():
        field_meta = fields_meta.get(fname, {})
        required = field_meta.get("required", False)
        ftype = field_meta.get("field_type", "scalar")
        source_cls = field_meta.get("source_classification", "")

        if fval is not None:
            ok_fields.append(fname)
            tag = "[OK]"
        elif required:
            null_required.append(fname)
            tag = "[MISSING*]"
        else:
            null_optional.append(fname)
            tag = "[MISSING]"

        # Format the value preview
        if fval is None:
            val_str = "null"
        elif isinstance(fval, list):
            if len(fval) == 0:
                val_str = "[]"
            elif isinstance(fval[0], dict):
                val_str = f"[array_object: {len(fval)} entries]"
            else:
                joined = " | ".join(str(v) for v in fval[:3])
                if len(fval) > 3:
                    joined += f" ... (+{len(fval)-3} more)"
                val_str = f"[{joined}]"
        else:
            val_str = str(fval)

        if len(val_str) > 100:
            val_str = val_str[:100] + "..."

        cls_tag = f"({source_cls})" if source_cls else ""
        print(f"  {tag:<12} [{ftype:<16}] {fname} {cls_tag}")
        if fval is not None:
            print(f"             -> {val_str}")
        print()

    print(f"{'='*70}")
    print(f"  Populated : {len(ok_fields)}/{len(filled_values)}")
    if null_required:
        print(
            f"  Missing * : {len(null_required)} required fields (recruiter-supplied):"
        )
        for f in null_required:
            print(f"              - {f}")
    if null_optional:
        print(f"  Missing   : {len(null_optional)} optional fields")
    print(f"{'='*70}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Format a resume against an existing template and download the DOCX"
    )
    parser.add_argument(
        "--template-id",
        required=True,
        help="Template ID from the database (use run_live_template_analysis.py to get one)",
    )
    parser.add_argument(
        "--resume",
        nargs="+",
        required=True,
        help="Path to the candidate resume file (PDF, DOCX, TXT, etc. — spaces allowed)",
    )
    parser.add_argument(
        "--output",
        default="formatted_resume_output.docx",
        help="Output path for the formatted DOCX (default: formatted_resume_output.docx)",
    )
    parser.add_argument(
        "--host",
        default="http://localhost:8000",
        help="Base URL of the API (default: http://localhost:8000)",
    )
    args = parser.parse_args()

    resume_path = Path(" ".join(args.resume))
    if not resume_path.exists():
        print(f"ERROR: Resume file not found: {resume_path}")
        sys.exit(1)

    output_path = Path(args.output)

    print("=" * 70)
    print("LIVE RESUME FORMAT")
    print("=" * 70)
    print(f"  Resume      : {resume_path}")
    print(f"  Template ID : {args.template_id}")
    print(f"  Output      : {output_path}")
    print(f"  API         : {args.host}")

    # 1. Submit format job (upload resume + template_id)
    job_id = submit_format_job(args.template_id, resume_path, args.host)

    # 2. Poll until done
    job = poll_format_job(job_id, args.host)

    # 3. Download the formatted DOCX
    download_docx(job_id, output_path, args.host)

    # 4. Print the filled manifest
    print_filled_manifest(job)

    print("=" * 70)
    print("DONE — Resume formatted successfully!")
    print(f"  Job ID : {job_id}")
    print(f"  Output : {output_path.absolute()}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
