from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

# Add workspace root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.absolute()))


def upload_template_to_api(template_path: Path) -> str:
    """Uploads a DOCX template file to the API and waits for the analysis job to complete."""
    url = "http://localhost:8000/admin/templates"
    print(f"\n[Template Upload] Uploading template {template_path.name} to {url}...")
    
    boundary = "WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{template_path.name}"\r\n'.encode("utf-8"))
    body.extend(b"Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document\r\n\r\n")
    body.extend(template_path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}"
        }
    )
    
    try:
        with urllib.request.urlopen(req) as res:
            response_data = json.loads(res.read().decode("utf-8"))
            template_id = response_data["template_id"]
            analysis_job_id = response_data["analysis_job_id"]
            print(f"[Template Upload] Success! Template ID: {template_id}, Analysis Job ID: {analysis_job_id}")
    except Exception as e:
        print(f"[Template Upload] Failed to upload template: {e}")
        sys.exit(1)
        
    # Poll for template analysis job completion
    status_url = f"http://localhost:8000/jobs/{analysis_job_id}"
    print(f"[Template Analysis] Polling job status at {status_url}...")
    
    while True:
        try:
            req_status = urllib.request.Request(status_url)
            with urllib.request.urlopen(req_status) as res:
                job_data = json.loads(res.read().decode("utf-8"))
                status = job_data["status"]
                time_str = datetime.now().strftime("%H:%M:%S")
                print(f"[{time_str}] Template Analysis Status: {status}")
                
                if status == "completed":
                    print("[Template Analysis] Manifest generated and saved in database successfully.")
                    return template_id
                elif status == "failed":
                    print(f"[Template Analysis] Job FAILED: {job_data.get('error')}")
                    sys.exit(1)
        except Exception as e:
            print(f"[Template Analysis] Polling error: {e}")
            
        time.sleep(2)


def submit_resume_format_job(template_id: str, resume_path: Path) -> str:
    """Submits the resume formatting job by uploading the resume file directly to the API."""
    url = "http://localhost:8000/format"
    print(f"\n[Format Submission] Uploading resume {resume_path.name} directly to {url}...")
    
    boundary = "WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = bytearray()
    
    # Add file field
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{resume_path.name}"\r\n'.encode("utf-8"))
    
    # Resolve mime type based on file extension
    ext = resume_path.suffix.lower()
    if ext == ".pdf":
        mime = "application/pdf"
    elif ext == ".docx":
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif ext == ".doc":
        mime = "application/msword"
    else:
        mime = "text/plain"
        
    body.extend(f"Content-Type: {mime}\r\n\r\n".encode("utf-8"))
    body.extend(resume_path.read_bytes())
    body.extend(b"\r\n")
    
    # Add template_id field
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(f'Content-Disposition: form-data; name="template_id"\r\n\r\n'.encode("utf-8"))
    body.extend(f"{template_id}\r\n".encode("utf-8"))
    
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}"
        }
    )
    
    try:
        with urllib.request.urlopen(req) as res:
            response_data = json.loads(res.read().decode("utf-8"))
            job_id = response_data["job_id"]
            print(f"[Format Submission] Job successfully queued! Job ID: {job_id}")
            return job_id
    except Exception as e:
        print(f"[Format Submission] Failed to submit formatting job: {e}")
        sys.exit(1)


def poll_job_status(job_id: str) -> dict:
    """Polls the job status until it completes or fails."""
    url = f"http://localhost:8000/jobs/{job_id}"
    print(f"[Formatting Polling] Polling job status at {url}...")
    
    while True:
        req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req) as res:
                job_data = json.loads(res.read().decode("utf-8"))
                status = job_data["status"]
                time_str = datetime.now().strftime("%H:%M:%S")
                print(f"[{time_str}] Formatting Job Status: {status}")
                
                if status in ["completed", "failed"]:
                    return job_data
        except Exception as e:
            print(f"[Formatting Polling] Polling error: {e}")
            
        time.sleep(3)


def download_resume(job_id: str, output_path: Path):
    """Downloads the completed document from the API."""
    url = f"http://localhost:8000/jobs/{job_id}/download"
    print(f"\n[Download] Downloading finished document from {url}...")
    
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as res:
        file_bytes = res.read()
        output_path.write_bytes(file_bytes)
        print(f"[Download] Success! Formatted resume saved cleanly to: {output_path.absolute()}")


def main():
    parser = argparse.ArgumentParser(description="Run Live End-to-End Resume Formatting Pipeline")
    parser.add_argument(
        "--resume",
        type=str,
        default="SampleData/orginal_data/Divyang_Panchasara-2026.pdf",
        help="Path to the local resume file (PDF, DOCX, TXT, etc.)"
    )
    parser.add_argument(
        "--template-id",
        type=str,
        default=None,
        help="The target Template ID stored in the system (optional if --template-file is specified)"
    )
    parser.add_argument(
        "--template-file",
        type=str,
        default=None,
        help="Path to a local DOCX template file to analyze and use (optional if --template-id is specified)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="formatted_resume_output.docx",
        help="Local output path to save the completed DOCX document"
    )
    
    args = parser.parse_args()
    
    resume_path = Path(args.resume)
    if not resume_path.exists():
        print(f"Error: Local resume file not found at: {resume_path}")
        sys.exit(1)
        
    print("==========================================================")
    print("RUNNING LIVE END-TO-END RESUME FORMATTING PIPELINE (PURE API)")
    print("==========================================================\n")
    
    # 1. Resolve template ID (Upload template first if specified, or if no ID/file is provided, use default sample)
    template_id = args.template_id
    if not template_id:
        template_file_path = args.template_file
        if not template_file_path:
            # Zero-config default: Upload sample Software Engineer template
            template_file_path = "SampleData/templates/template_1_Software_Engineer.docx"
            print(f"[Info] No template_id or template_file specified. Using default: {template_file_path}")
            
        t_path = Path(template_file_path)
        if not t_path.exists():
            print(f"Error: Template file not found at: {t_path}")
            sys.exit(1)
        
        template_id = upload_template_to_api(t_path)
    else:
        print(f"[Template] Using pre-specified Template ID: {template_id}")
    
    # 2. Submit the format job via FastAPI (direct file upload!)
    job_id = submit_resume_format_job(template_id, resume_path)
    
    # 3. Poll for completion
    job_data = poll_job_status(job_id)
    
    if job_data["status"] == "failed":
        print(f"\nPipeline Execution FAILED: {job_data.get('error')}")
        sys.exit(1)
        
    # 4. Download and save the finished DOCX document
    output_file = Path(args.output)
    download_resume(job_id, output_file)

    # 5. Print the filled manifest from the job record
    print("\n=== FILLED MANIFEST (extracted_data) ===")
    extracted_data = job_data.get("extracted_data")
    if extracted_data:
        filled_values = extracted_data.get("filled_values", extracted_data)
        fields_meta = {f["name"]: f for f in extracted_data.get("fields", [])}
        null_required = []
        for fname, fval in filled_values.items():
            field_meta = fields_meta.get(fname, {})
            required = field_meta.get("required", False)
            ftype = field_meta.get("field_type", "scalar")
            val_repr = repr(fval) if isinstance(fval, (list, dict)) else str(fval)
            if len(val_repr) > 120:
                val_repr = val_repr[:120] + "..."
            status_icon = "[OK]" if fval is not None else ("[MISSING*]" if required else "[MISSING]")
            print(f"  {status_icon} [{ftype:14s}] {fname}: {val_repr}")
            if fval is None and required:
                null_required.append(fname)
        if null_required:
            print(f"\n  WARNING: {len(null_required)} required fields are null: {null_required}")
        else:
            print(f"\n  All required fields populated!")
    else:
        print("  (No extracted_data stored on job)")

    print("\n==========================================================")
    print("PIPELINE RUN SUCCESSFULLY FINISHED!")
    print("==========================================================")


if __name__ == "__main__":
    main()
