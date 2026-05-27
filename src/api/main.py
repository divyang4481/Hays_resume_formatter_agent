from __future__ import annotations

from datetime import datetime, timezone
import io
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, Request, Form
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.shared.models import (
    JobStatus,
    JobStatusResponse,
    JobListResponse,
    JobType,
    ResumeFormatMessage,
    ResumeFormatRequest,
    ResumeFormatResponse,
    TemplateAnalysisMessage,
    TemplateCreateResponse,
    TemplateListResponse,
    TemplateDetailResponse,
)
from src.shared.queue import queue_bus
from src.shared.repository import repo
from src.shared.storage import object_store

app = FastAPI(title="Hays Resume Formatter API", version="0.1.0")


class SelectTemplateRequest(BaseModel):
    template_id: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


@app.post("/admin/templates", response_model=TemplateCreateResponse)
async def upload_template(file: UploadFile = File(...)) -> TemplateCreateResponse:
    if not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only DOCX templates are supported in MVP")

    content = await file.read()
    template_name = Path(file.filename).name
    object_key = f"templates/{template_name}"
    object_store.put_bytes(object_key, content)

    template_id, version = repo.create_template(template_name=template_name, object_key=object_key)
    job = repo.create_job(JobType.TEMPLATE_ANALYSIS)

    queue_bus.push_template_analysis(
        TemplateAnalysisMessage(
            job_id=job.job_id,
            template_id=template_id,
            template_object_key=object_key,
            template_name=template_name,
        ).model_dump()
    )

    return TemplateCreateResponse(
        template_id=template_id,
        version=version,
        status=JobStatus.QUEUED,
        analysis_job_id=job.job_id,
    )


@app.post("/format", response_model=ResumeFormatResponse)
async def submit_format_job(request: Request) -> ResumeFormatResponse:
    content_type = request.headers.get("content-type", "")
    template_id = None
    resume_text = None
    resume_object_key = None

    if "application/json" in content_type:
        body = await request.json()
        template_id = body.get("template_id")
        resume_text = body.get("resume_text")
        resume_object_key = body.get("resume_object_key")
    elif "multipart/form-data" in content_type:
        form = await request.form()
        print(f"[API Debug] form keys: {list(form.keys())}")
        template_id = form.get("template_id")
        resume_text = form.get("resume_text")
        resume_object_key = form.get("resume_object_key")
        
        file = form.get("file")
        print(f"[API Debug] file: {file}, type: {type(file)}")
        if file and hasattr(file, "filename") and file.filename:
            print(f"[API Debug] file filename: {file.filename}")
            # Direct file upload! Save the uploaded resume to the S3 bucket / storage layer
            file_content = await file.read()
            resume_name = Path(file.filename).name
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            resume_object_key = f"resumes/{timestamp}_{resume_name}"
            
            # Save the file cleanly into our object store
            object_store.put_bytes(resume_object_key, file_content)
    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported Content-Type. Please use application/json or multipart/form-data."
        )

    if template_id:
        template = repo.get_template(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

    job = repo.create_job(
        JobType.RESUME_FORMAT,
        template_id=template_id,
        resume_text=resume_text,
        resume_object_key=resume_object_key,
    )
    message = ResumeFormatMessage(
        job_id=job.job_id,
        template_id=template_id,
        resume_text=resume_text,
        resume_object_key=resume_object_key,
    )
    queue_bus.push_resume_format(message.model_dump())

    return ResumeFormatResponse(job_id=job.job_id, status=JobStatus.QUEUED)


@app.post("/jobs/{job_id}/select-template", response_model=ResumeFormatResponse)
def select_template(job_id: str, request: SelectTemplateRequest) -> ResumeFormatResponse:
    job = repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.WAITING_FOR_TEMPLATE_SELECTION:
        raise HTTPException(
            status_code=400,
            detail=f"Job is not in waiting_for_template_selection state. Current state: {job.status.value}"
        )

    template = repo.get_template(request.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    repo.update_job(job_id, status=JobStatus.QUEUED, template_id=request.template_id)

    message = ResumeFormatMessage(
        job_id=job_id,
        template_id=request.template_id,
        resume_text=job.resume_text,
        resume_object_key=job.resume_object_key,
    )
    queue_bus.push_resume_format(message.model_dump())

    return ResumeFormatResponse(job_id=job_id, status=JobStatus.QUEUED)


@app.get("/jobs", response_model=JobListResponse)
def list_jobs(
    template_id: str | None = None,
    status: JobStatus | None = None,
    limit: int = 10,
    offset: int = 0,
) -> JobListResponse:
    total, jobs = repo.list_jobs(template_id=template_id, status=status, limit=limit, offset=offset)
    return JobListResponse(total=total, limit=limit, offset=offset, jobs=jobs)


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str) -> JobStatusResponse:
    job = repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/jobs/{job_id}/download")
def download_resume(job_id: str):
    job = repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job is not completed yet. Current status: {job.status.value}"
        )

    if not job.output_object_key:
        raise HTTPException(status_code=404, detail="Formatted resume file not found")

    try:
        file_bytes = object_store.get_bytes(job.output_object_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch file from storage: {e}")

    # Return docx stream for attachment download
    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={job_id}.docx"}
    )


@app.get("/templates/{template_id}/manifest")
def get_template_manifest(template_id: str) -> dict:
    manifest = repo.get_manifest(template_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Manifest not found")
    return manifest


@app.get("/templates", response_model=TemplateListResponse)
def list_templates(limit: int = 10, offset: int = 0) -> TemplateListResponse:
    total, templates = repo.list_templates(limit=limit, offset=offset)
    return TemplateListResponse(total=total, limit=limit, offset=offset, templates=templates)


@app.get("/templates/{template_id}", response_model=TemplateDetailResponse)
def get_template_details(template_id: str) -> TemplateDetailResponse:
    template = repo.get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    manifest = repo.get_manifest(template_id)
    return TemplateDetailResponse(
        template_id=template_id,
        template_name=template["template_name"],
        object_key=template["object_key"],
        version=template["version"],
        manifest=manifest,
    )


app.mount("/", StaticFiles(directory="src/frontend", html=True), name="frontend")

