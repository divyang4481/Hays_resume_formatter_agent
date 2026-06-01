from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class JobType(str, Enum):
    TEMPLATE_ANALYSIS = "template_analysis"
    RESUME_FORMAT = "resume_format"


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"
    WAITING_FOR_TEMPLATE_SELECTION = "waiting_for_template_selection"


class TemplateCreateResponse(BaseModel):
    template_id: str
    version: int
    status: JobStatus
    analysis_job_id: str


class TemplateListItem(BaseModel):
    template_id: str
    template_name: str
    object_key: str
    version: int
    manifest: dict[str, Any] | None = None


class TemplateListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    templates: list[TemplateListItem]


class TemplateDetailResponse(BaseModel):
    template_id: str
    template_name: str
    object_key: str
    version: int
    manifest: dict[str, Any] | None = None


class ResumeFormatRequest(BaseModel):
    template_id: str | None = None
    resume_text: str | None = None
    resume_object_key: str | None = None


class ResumeFormatResponse(BaseModel):
    job_id: str
    status: JobStatus


class JobStatusResponse(BaseModel):
    job_id: str
    job_type: JobType
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    error: str | None = None
    output_object_key: str | None = None
    template_id: str | None = None
    resume_text: str | None = None
    resume_object_key: str | None = None
    resume_summary: str | None = None
    suggested_templates: list[dict] | None = None
    extracted_data: dict[str, Any] | None = None
    field_data_mapping: dict[str, Any] | None = None


class JobListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    jobs: list[JobStatusResponse]


class FieldDefinition(BaseModel):
    name: str
    field_type: str = Field(description="scalar|array|array_object")
    source_hint: str
    template_token: str
    required: bool = False
    formatting_hint: str | None = None


class FieldManifest(BaseModel):
    manifest_id: str
    template_id: str
    version: int
    fields: list[FieldDefinition]
    created_at: datetime


class TemplateAnalysisMessage(BaseModel):
    job_id: str
    template_id: str
    template_object_key: str
    template_name: str


class ResumeFormatMessage(BaseModel):
    job_id: str
    template_id: str | None = None
    resume_text: str | None = None
    resume_object_key: str | None = None


class GraphResult(BaseModel):
    status: JobStatus
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
