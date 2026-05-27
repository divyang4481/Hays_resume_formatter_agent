from __future__ import annotations

from datetime import datetime, timezone
import json
from threading import Lock
from typing import Any
from uuid import uuid4

from sqlalchemy import create_engine, text

from src.shared.config import settings
from .models import JobStatus, JobStatusResponse, JobType


class InMemoryRepository:
    def __init__(self) -> None:
        self._lock = Lock()
        self.templates: dict[str, dict[str, Any]] = {}
        self.manifests: dict[str, dict[str, Any]] = {}
        self.jobs: dict[str, JobStatusResponse] = {}
        self.llm_calls: list[dict[str, Any]] = []

    def save_llm_call(
        self,
        *,
        model_id: str,
        prompt_system: str,
        prompt_user: str,
        input_tokens: int,
        output_tokens: int,
        latency_seconds: float,
    ) -> str:
        call_id = str(uuid4())
        with self._lock:
            self.llm_calls.append({
                "call_id": call_id,
                "model_id": model_id,
                "prompt_system": prompt_system,
                "prompt_user": prompt_user,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "latency_seconds": latency_seconds,
                "created_at": datetime.now(timezone.utc),
            })
        return call_id

    def create_template(self, *, template_name: str, object_key: str) -> tuple[str, int]:
        with self._lock:
            template_id = str(uuid4())
            self.templates[template_id] = {
                "template_name": template_name,
                "object_key": object_key,
                "version": 1,
            }
            return template_id, 1

    def get_template(self, template_id: str) -> dict[str, Any] | None:
        tpl = self.templates.get(template_id)
        if not tpl:
            return None
        return {
            "template_id": template_id,
            "template_name": tpl["template_name"],
            "object_key": tpl["object_key"],
            "version": tpl["version"],
        }

    def list_templates(
        self,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> tuple[int, list[dict[str, Any]]]:
        with self._lock:
            items = []
            for tid, tpl in self.templates.items():
                manifest = self.manifests.get(tid)
                items.append({
                    "template_id": tid,
                    "template_name": tpl["template_name"],
                    "object_key": tpl["object_key"],
                    "version": tpl["version"],
                    "manifest": manifest,
                })
            
            # Sort by name
            items.sort(key=lambda t: t["template_name"])
            total = len(items)
            paginated = items[offset : offset + limit]
            return total, paginated

    def save_manifest(self, template_id: str, manifest: dict[str, Any]) -> None:
        with self._lock:
            self.manifests[template_id] = manifest

    def get_manifest(self, template_id: str) -> dict[str, Any] | None:
        return self.manifests.get(template_id)

    def create_job(
        self,
        job_type: JobType,
        template_id: str | None = None,
        resume_text: str | None = None,
        resume_object_key: str | None = None,
    ) -> JobStatusResponse:
        now = datetime.now(timezone.utc)
        job = JobStatusResponse(
            job_id=str(uuid4()),
            job_type=job_type,
            status=JobStatus.QUEUED,
            created_at=now,
            updated_at=now,
            template_id=template_id,
            resume_text=resume_text,
            resume_object_key=resume_object_key,
        )
        with self._lock:
            self.jobs[job.job_id] = job
        return job

    def update_job(
        self,
        job_id: str,
        *,
        status: JobStatus,
        error: str | None = None,
        output_object_key: str | None = None,
        template_id: str | None = None,
        suggested_templates: list[dict] | None = None,
        extracted_data: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            current = self.jobs[job_id]
            self.jobs[job_id] = current.model_copy(
                update={
                    "status": status,
                    "updated_at": datetime.now(timezone.utc),
                    "error": error,
                    "output_object_key": output_object_key,
                    "template_id": template_id if template_id is not None else current.template_id,
                    "suggested_templates": suggested_templates if suggested_templates is not None else current.suggested_templates,
                    "extracted_data": extracted_data if extracted_data is not None else current.extracted_data,
                }
            )

    def get_job(self, job_id: str) -> JobStatusResponse | None:
        return self.jobs.get(job_id)

    def list_jobs(
        self,
        *,
        template_id: str | None = None,
        status: JobStatus | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> tuple[int, list[JobStatusResponse]]:
        with self._lock:
            filtered = list(self.jobs.values())
            
        if template_id:
            filtered = [j for j in filtered if j.template_id == template_id]
        if status:
            filtered = [j for j in filtered if j.status == status]
            
        # Sort descending (created_at DESC)
        filtered.sort(key=lambda j: j.created_at, reverse=True)
        
        total = len(filtered)
        paginated = filtered[offset : offset + limit]
        return total, paginated


class PostgresRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self._init_schema()

    def _init_schema(self) -> None:
        ddl = """
        CREATE TABLE IF NOT EXISTS templates (
            template_id TEXT PRIMARY KEY,
            template_name TEXT NOT NULL,
            object_key TEXT NOT NULL,
            version INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS manifests (
            template_id TEXT PRIMARY KEY,
            manifest_json JSONB NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            job_type TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            error TEXT NULL,
            output_object_key TEXT NULL,
            template_id TEXT NULL,
            resume_text TEXT NULL,
            resume_object_key TEXT NULL,
            suggested_templates JSONB NULL,
            extracted_data JSONB NULL
        );

        CREATE TABLE IF NOT EXISTS llm_calls (
            call_id TEXT PRIMARY KEY,
            model_id TEXT NOT NULL,
            prompt_system TEXT,
            prompt_user TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            latency_seconds REAL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
        with self.engine.begin() as conn:
            conn.execute(text(ddl))

    def create_template(self, *, template_name: str, object_key: str) -> tuple[str, int]:
        template_id = str(uuid4())
        version = 1
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO templates (template_id, template_name, object_key, version)
                    VALUES (:template_id, :template_name, :object_key, :version)
                    """
                ),
                {
                    "template_id": template_id,
                    "template_name": template_name,
                    "object_key": object_key,
                    "version": version,
                },
            )
        return template_id, version

    def get_template(self, template_id: str) -> dict[str, Any] | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                text("SELECT template_id, template_name, object_key, version FROM templates WHERE template_id = :template_id"),
                {"template_id": template_id},
            ).mappings().first()
        return dict(row) if row else None

    def list_templates(
        self,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> tuple[int, list[dict[str, Any]]]:
        query = """
            SELECT t.template_id, t.template_name, t.object_key, t.version, m.manifest_json as manifest
            FROM templates t
            LEFT JOIN manifests m ON t.template_id = m.template_id
            ORDER BY t.template_name ASC
            LIMIT :limit OFFSET :offset
        """
        count_query = "SELECT COUNT(*) FROM templates"
        params = {"limit": limit, "offset": offset}
        with self.engine.begin() as conn:
            total = conn.execute(text(count_query)).scalar() or 0
            rows = conn.execute(text(query), params).mappings().all()
            
        items = []
        for r in rows:
            manifest = r["manifest"]
            if isinstance(manifest, str):
                manifest = json.loads(manifest)
            items.append({
                "template_id": r["template_id"],
                "template_name": r["template_name"],
                "object_key": r["object_key"],
                "version": r["version"],
                "manifest": manifest,
            })
        return total, items

    def save_manifest(self, template_id: str, manifest: dict[str, Any]) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO manifests (template_id, manifest_json, updated_at)
                    VALUES (:template_id, CAST(:manifest_json AS JSONB), NOW())
                    ON CONFLICT (template_id)
                    DO UPDATE SET manifest_json = EXCLUDED.manifest_json, updated_at = NOW()
                    """
                ),
                {"template_id": template_id, "manifest_json": json.dumps(manifest)},
            )

    def get_manifest(self, template_id: str) -> dict[str, Any] | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                text("SELECT manifest_json FROM manifests WHERE template_id = :template_id"),
                {"template_id": template_id},
            ).first()
        return row[0] if row else None

    def create_job(
        self,
        job_type: JobType,
        template_id: str | None = None,
        resume_text: str | None = None,
        resume_object_key: str | None = None,
    ) -> JobStatusResponse:
        now = datetime.now(timezone.utc)
        job = JobStatusResponse(
            job_id=str(uuid4()),
            job_type=job_type,
            status=JobStatus.QUEUED,
            created_at=now,
            updated_at=now,
            template_id=template_id,
            resume_text=resume_text,
            resume_object_key=resume_object_key,
        )
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO jobs (job_id, job_type, status, created_at, updated_at, error, output_object_key, template_id, resume_text, resume_object_key, suggested_templates, extracted_data)
                    VALUES (:job_id, :job_type, :status, :created_at, :updated_at, :error, :output_object_key, :template_id, :resume_text, :resume_object_key, :suggested_templates, :extracted_data)
                    """
                ),
                {
                    "job_id": job.job_id,
                    "job_type": job.job_type.value,
                    "status": job.status.value,
                    "created_at": job.created_at,
                    "updated_at": job.updated_at,
                    "error": job.error,
                    "output_object_key": job.output_object_key,
                    "template_id": job.template_id,
                    "resume_text": job.resume_text,
                    "resume_object_key": job.resume_object_key,
                    "suggested_templates": json.dumps(job.suggested_templates) if job.suggested_templates else None,
                    "extracted_data": None,
                },
            )
        return job

    def update_job(
        self,
        job_id: str,
        *,
        status: JobStatus,
        error: str | None = None,
        output_object_key: str | None = None,
        template_id: str | None = None,
        suggested_templates: list[dict] | None = None,
        extracted_data: dict[str, Any] | None = None,
    ) -> None:
        with self.engine.begin() as conn:
            row = conn.execute(
                text("SELECT template_id, suggested_templates, extracted_data FROM jobs WHERE job_id = :job_id"),
                {"job_id": job_id}
            ).mappings().first()
            
            existing_template_id = row["template_id"] if row else None
            existing_suggested_templates = row["suggested_templates"] if row else None
            existing_extracted_data = row["extracted_data"] if row else None
            
            final_template_id = template_id if template_id is not None else existing_template_id
            
            if suggested_templates is not None:
                final_suggested_templates = json.dumps(suggested_templates)
            elif existing_suggested_templates is not None:
                if isinstance(existing_suggested_templates, str):
                    final_suggested_templates = existing_suggested_templates
                else:
                    final_suggested_templates = json.dumps(existing_suggested_templates)
            else:
                final_suggested_templates = None

            if extracted_data is not None:
                final_extracted_data = json.dumps(extracted_data)
            elif existing_extracted_data is not None:
                if isinstance(existing_extracted_data, str):
                    final_extracted_data = existing_extracted_data
                else:
                    final_extracted_data = json.dumps(existing_extracted_data)
            else:
                final_extracted_data = None

            conn.execute(
                text(
                    """
                    UPDATE jobs
                    SET status = :status,
                        updated_at = :updated_at,
                        error = :error,
                        output_object_key = :output_object_key,
                        template_id = :template_id,
                        suggested_templates = CAST(:suggested_templates AS JSONB),
                        extracted_data = CAST(:extracted_data AS JSONB)
                    WHERE job_id = :job_id
                    """
                ),
                {
                    "job_id": job_id,
                    "status": status.value,
                    "updated_at": datetime.now(timezone.utc),
                    "error": error,
                    "output_object_key": output_object_key,
                    "template_id": final_template_id,
                    "suggested_templates": final_suggested_templates,
                    "extracted_data": final_extracted_data,
                },
            )

    def get_job(self, job_id: str) -> JobStatusResponse | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT job_id, job_type, status, created_at, updated_at, error, output_object_key, template_id, resume_text, resume_object_key, suggested_templates, extracted_data
                    FROM jobs WHERE job_id = :job_id
                    """
                ),
                {"job_id": job_id},
            ).mappings().first()
        if not row:
            return None
            
        suggested = row["suggested_templates"]
        if isinstance(suggested, str):
            suggested_list = json.loads(suggested)
        elif suggested is not None:
            suggested_list = list(suggested)
        else:
            suggested_list = None

        extracted = row["extracted_data"]
        if isinstance(extracted, str):
            extracted_dict = json.loads(extracted)
        elif extracted is not None:
            extracted_dict = dict(extracted)
        else:
            extracted_dict = None

        return JobStatusResponse(
            job_id=row["job_id"],
            job_type=JobType(row["job_type"]),
            status=JobStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            error=row["error"],
            output_object_key=row["output_object_key"],
            template_id=row["template_id"],
            resume_text=row["resume_text"],
            resume_object_key=row["resume_object_key"],
            suggested_templates=suggested_list,
            extracted_data=extracted_dict,
        )

    def list_jobs(
        self,
        *,
        template_id: str | None = None,
        status: JobStatus | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> tuple[int, list[JobStatusResponse]]:
        query_parts = ["SELECT * FROM jobs"]
        count_parts = ["SELECT COUNT(*) FROM jobs"]
        where_parts = []
        params = {"limit": limit, "offset": offset}
        
        if template_id:
            where_parts.append("template_id = :template_id")
            params["template_id"] = template_id
        if status:
            where_parts.append("status = :status")
            params["status"] = status.value

        if where_parts:
            where_clause = " WHERE " + " AND ".join(where_parts)
            query_parts.append(where_clause)
            count_parts.append(where_clause)

        query_parts.append(" ORDER BY created_at DESC LIMIT :limit OFFSET :offset")
        
        with self.engine.begin() as conn:
            # Get total count
            total_count = conn.execute(text("".join(count_parts)), params).scalar() or 0
            
            # Get records
            rows = conn.execute(text("".join(query_parts)), params).mappings().all()

        jobs = []
        for row in rows:
            suggested = row["suggested_templates"]
            if isinstance(suggested, str):
                suggested_list = json.loads(suggested)
            elif suggested is not None:
                suggested_list = list(suggested)
            else:
                suggested_list = None

            extracted = row["extracted_data"]
            if isinstance(extracted, str):
                extracted_dict = json.loads(extracted)
            elif extracted is not None:
                extracted_dict = dict(extracted)
            else:
                extracted_dict = None

            jobs.append(
                JobStatusResponse(
                    job_id=row["job_id"],
                    job_type=JobType(row["job_type"]),
                    status=JobStatus(row["status"]),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    error=row["error"],
                    output_object_key=row["output_object_key"],
                    template_id=row["template_id"],
                    resume_text=row["resume_text"],
                    resume_object_key=row["resume_object_key"],
                    suggested_templates=suggested_list,
                    extracted_data=extracted_dict,
                )
            )
            
        return total_count, jobs

    def save_llm_call(
        self,
        *,
        model_id: str,
        prompt_system: str,
        prompt_user: str,
        input_tokens: int,
        output_tokens: int,
        latency_seconds: float,
    ) -> str:
        call_id = str(uuid4())
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO llm_calls (call_id, model_id, prompt_system, prompt_user, input_tokens, output_tokens, latency_seconds, created_at)
                    VALUES (:call_id, :model_id, :prompt_system, :prompt_user, :input_tokens, :output_tokens, :latency_seconds, NOW())
                    """
                ),
                {
                    "call_id": call_id,
                    "model_id": model_id,
                    "prompt_system": prompt_system,
                    "prompt_user": prompt_user,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "latency_seconds": latency_seconds,
                },
            )
        return call_id


repo = PostgresRepository(settings.database_url) if settings.use_aws_services else InMemoryRepository()
