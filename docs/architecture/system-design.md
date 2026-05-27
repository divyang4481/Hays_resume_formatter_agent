# System Design (MVP)

## Components

1. Frontend
   - Admin area: upload DOCX templates.
   - User area: submit resume + template, track job, download output.
2. Core API
   - Accepts uploads and job requests.
   - Stores files in object store.
   - Persists metadata and enqueues worker messages.
   - Exposes internal MCP/A2A adapters in future phases.
3. Worker
   - Template analysis graph -> field manifest.
   - Resume formatting graph -> deterministic output.

## Data Services

- S3: templates, resumes, manifests, outputs.
- RDS: templates, manifests, jobs, telemetry.
- SQS: template-analysis and resume-format queues.

## LLM Usage

- Semantic template analysis.
- Structured extraction from resume.
- Rendering is deterministic and non-generative.
