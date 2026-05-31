from __future__ import annotations

from datetime import datetime, timezone
import io
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.shared.models import (
    JobStatus,
    JobStatusResponse,
    JobListResponse,
    JobType,
    ResumeFormatMessage,
    ResumeFormatResponse,
    TemplateAnalysisMessage,
    TemplateCreateResponse,
    TemplateListResponse,
    TemplateDetailResponse,
)
from src.shared.config import settings
from src.shared.queue import queue_bus
from src.shared.repository import repo
from src.shared.storage import object_store

app = FastAPI(title="Hays Resume Formatter API", version="0.1.0")

allowed_origins = [origin.strip() for origin in settings.cors_allow_origins.split(",") if origin.strip()]
if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def support_api_path_prefix(request: Request, call_next):
    """Allow ECS/ALB deployments to expose this service below /api.

    The API container remains API-only. This middleware only normalizes the
    incoming path when an external router forwards /api/* without stripping the
    prefix, so both local `/health` and ECS `/api/health` work.
    """

    path = request.scope.get("path", "")
    if path == "/api":
        request.scope["path"] = "/health"
    elif path.startswith("/api/"):
        request.scope["path"] = path[4:]
    return await call_next(request)


class SelectTemplateRequest(BaseModel):
    template_id: str


FORMAT_REQUEST_BODY_OPENAPI = {
    "required": True,
    "content": {
        "application/json": {
            "schema": {
                "type": "object",
                "properties": {
                    "template_id": {
                        "type": "string",
                        "description": "Optional template ID. If omitted, the job may pause for template selection.",
                    },
                    "resume_text": {
                        "type": "string",
                        "description": "Raw candidate resume text.",
                    },
                    "resume_object_key": {
                        "type": "string",
                        "description": "Existing object-store key for an already-uploaded resume.",
                    },
                },
            },
            "examples": {
                "resumeText": {
                    "summary": "Submit plain resume text",
                    "value": {
                        "template_id": "template-uuid",
                        "resume_text": "John Doe\njohn@example.com\n...",
                    },
                },
                "existingObject": {
                    "summary": "Submit existing object key",
                    "value": {
                        "template_id": "template-uuid",
                        "resume_object_key": "resumes/candidate.pdf",
                    },
                },
            },
        },
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "properties": {
                    "template_id": {
                        "type": "string",
                        "description": "Optional template ID. If omitted, the job may pause for template selection.",
                    },
                    "resume_text": {
                        "type": "string",
                        "description": "Optional pasted resume text to submit with or instead of a file.",
                    },
                    "resume_object_key": {
                        "type": "string",
                        "description": "Optional existing object-store key. Usually omitted when uploading a file.",
                    },
                    "file": {
                        "type": "string",
                        "format": "binary",
                        "description": "Candidate resume file. Supports PDF, DOCX, or TXT.",
                    },
                },
            },
        },
    },
}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


@app.post(
    "/admin/templates",
    response_model=TemplateCreateResponse,
    summary="Upload a DOCX template for analysis",
)
async def upload_template(
    file: UploadFile = File(..., description="DOCX template file to analyze and register")
) -> TemplateCreateResponse:
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


def create_resume_format_job(
    *,
    template_id: str | None,
    resume_text: str | None,
    resume_object_key: str | None,
) -> ResumeFormatResponse:
    if template_id:
        template = repo.get_template(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

    if not resume_text and not resume_object_key:
        raise HTTPException(
            status_code=400,
            detail="Provide resume_text, resume_object_key, or upload a resume file.",
        )

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


def build_resume_object_key(file: UploadFile) -> str:
    resume_name = Path(file.filename or "resume").name
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    resume_object_key = f"resumes/{timestamp}_{resume_name}"
    return resume_object_key


@app.post(
    "/format",
    response_model=ResumeFormatResponse,
    summary="Submit a resume formatting job",
    description=(
        "Supports both existing JSON clients and Swagger/browser multipart uploads. "
        "Use JSON with resume_text or resume_object_key, or multipart/form-data with a resume file."
    ),
    openapi_extra={"requestBody": FORMAT_REQUEST_BODY_OPENAPI},
)
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
        template_id = form.get("template_id")
        resume_text = form.get("resume_text")
        resume_object_key = form.get("resume_object_key")

        file = form.get("file")
        if file and hasattr(file, "filename") and file.filename:
            resume_object_key = build_resume_object_key(file)
            object_store.put_bytes(resume_object_key, await file.read())
    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported Content-Type. Please use application/json or multipart/form-data."
        )

    return create_resume_format_job(
        template_id=template_id,
        resume_text=resume_text,
        resume_object_key=resume_object_key,
    )


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

