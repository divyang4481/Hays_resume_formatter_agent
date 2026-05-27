from __future__ import annotations

import time

from src.shared.extractor import extract_text_from_bytes
from src.shared.models import JobStatus, ResumeFormatMessage, TemplateAnalysisMessage
from src.shared.queue import queue_bus
from src.shared.repository import repo
from src.shared.storage import object_store
from src.worker.agents.template_analysis import run_template_analysis
from src.worker.agents.resume_formatter import run_resume_format


def process_template_analysis(message: dict) -> None:
    try:
        print(f"Processing template analysis job: {message.get('job_id')}")
        payload = TemplateAnalysisMessage.model_validate(message)
        repo.update_job(payload.job_id, status=JobStatus.PROCESSING)

        result = run_template_analysis(
            template_id=payload.template_id,
            template_name=payload.template_name,
            template_object_key=payload.template_object_key,
        )

        if result.status == JobStatus.COMPLETED:
            repo.save_manifest(payload.template_id, result.data)
            repo.update_job(payload.job_id, status=JobStatus.COMPLETED)
            print(f"Successfully completed template analysis job: {payload.job_id}")
            return

        repo.update_job(payload.job_id, status=JobStatus.FAILED, error=result.error)
        print(f"Template analysis job {payload.job_id} failed: {result.error}")
    except Exception as e:
        print(f"Error processing template analysis: {e}")
        job_id = message.get("job_id")
        if job_id:
            try:
                repo.update_job(job_id, status=JobStatus.FAILED, error=str(e))
            except Exception as db_err:
                print(f"Failed to update job status to FAILED in DB: {db_err}")


def process_resume_format(message: dict) -> None:
    try:
        print(f"Processing resume formatting job: {message.get('job_id')}")
        payload = ResumeFormatMessage.model_validate(message)
        repo.update_job(payload.job_id, status=JobStatus.PROCESSING)

        result = run_resume_format(
            job_id=payload.job_id,
            template_id=payload.template_id,
            resume_text=payload.resume_text,
            resume_object_key=payload.resume_object_key,
        )

        if result.status == JobStatus.WAITING_FOR_TEMPLATE_SELECTION:
            repo.update_job(
                payload.job_id,
                status=JobStatus.WAITING_FOR_TEMPLATE_SELECTION,
                suggested_templates=result.data.get("suggested_templates", [])
            )
            print(f"Resume formatting job {payload.job_id} is waiting for template selection.")
            return

        if result.status != JobStatus.COMPLETED:
            repo.update_job(payload.job_id, status=JobStatus.FAILED, error=result.error)
            print(f"Resume formatting job {payload.job_id} failed: {result.error}")
            return

        output_key = f"outputs/{payload.job_id}.docx"
        object_store.put_bytes(output_key, result.data["rendered_bytes"])

        # Store the full filled manifest (field definitions + all filled values) as extracted_data.
        # Fall back to raw extracted dict if filled_manifest wasn't built (e.g. error path).
        filled_manifest = result.data.get("filled_manifest")
        extracted_data_to_store = filled_manifest if filled_manifest is not None else result.data.get("extracted")

        repo.update_job(
            payload.job_id,
            status=JobStatus.COMPLETED,
            output_object_key=output_key,
            template_id=result.data.get("template_id"),
            extracted_data=extracted_data_to_store,
        )
        print(f"Successfully completed resume formatting job: {payload.job_id}")
        if filled_manifest:
            filled_count = sum(1 for v in filled_manifest.get("filled_values", {}).values() if v is not None)
            total_count = len(filled_manifest.get("fields", []))
            print(f"  Filled manifest: {filled_count}/{total_count} fields populated")
    except Exception as e:
        print(f"Error processing resume format: {e}")
        job_id = message.get("job_id")
        if job_id:
            try:
                repo.update_job(job_id, status=JobStatus.FAILED, error=str(e))
            except Exception as db_err:
                print(f"Failed to update job status to FAILED in DB: {db_err}")


def run_worker_loop() -> None:
    print("Worker loop started")
    print("[TemplateAnalysis] pipeline_version=layout_v2_agentic_qc_2026_05_28")
    print("[TemplateAnalysis] graph_file=src/worker/agents/template_analysis/graph.py")
    while True:
        try:
            # Poll the template analysis queue
            analysis_msg = queue_bus.pop_template_analysis(timeout_seconds=0.2)
            if analysis_msg:
                # SQS Shared Queue check: distinguish by the presence of template_name
                if "template_name" in analysis_msg:
                    process_template_analysis(analysis_msg)
                else:
                    process_resume_format(analysis_msg)

            # Poll the resume format queue
            format_msg = queue_bus.pop_resume_format(timeout_seconds=0.2)
            if format_msg:
                # SQS Shared Queue check: distinguish by the presence of template_name
                if "template_name" in format_msg:
                    process_template_analysis(format_msg)
                else:
                    process_resume_format(format_msg)
        except Exception as e:
            print(f"Error in worker polling loop: {e}")
            # If the error is credential or signature-related, trigger boto3 SQS client recreation
            if "SignatureDoesNotMatch" in str(e) or "ExpiredToken" in str(e) or "credentials" in str(e).lower():
                try:
                    print("Recreating Boto3 SQS client to load fresh credentials...")
                    if hasattr(queue_bus, "recreate_client"):
                        queue_bus.recreate_client()
                except Exception as refresh_err:
                    print(f"Failed to recreate SQS client: {refresh_err}")
            time.sleep(5)  # Backoff sleep on transient network/SQS issues

        time.sleep(0.05)


if __name__ == "__main__":
    run_worker_loop()
