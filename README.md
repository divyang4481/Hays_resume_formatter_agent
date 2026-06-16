# Hays Resume Formatter Agent

MVP starter implementation for AWS-oriented resume formatting pipeline using API + worker architecture and LangGraph flows.

## What is implemented now

- FastAPI service for template upload and formatting job submission.
- Switchable adapters for local or AWS-backed runtime:
  - S3 object storage adapter
  - SQS queue adapter
  - PostgreSQL repository adapter
- Worker loop with two LangGraph flows:
  - Template analysis -> manifest creation
  - Resume extraction/render -> output artifact
- Bedrock-based template field inference with Agentic Core orchestration.
- Prompt manager using Jinja2 templates for system and user prompts.
- Shared models for API, jobs, queue payloads, and field manifest.
- Contracts and architecture docs under `docs/`.
- CloudFormation stack template for `resume-formatteragent-2` under `infra/cloudformation`.

## Project layout

- `src/api` - HTTP API
- `src/worker` - background worker and graph logic
- `src/shared` - config, schemas, storage, queue, repository
- `docs/contracts` - API/queue/manifest contracts
- `docs/architecture` - architecture notes
- `infra/cloudformation` - AWS stack templates and sample params
- `docker` - Docker image build files
- `scripts` - deploy, env bootstrap, and extraction demo scripts

## Deploy AWS Infrastructure (S3, SQS, RDS, ECR, ECS Fargate)

A comprehensive PowerShell orchestrator script `deploy-aws.ps1` is provided to deploy all 3 parts of the AWS CloudFormation infrastructure, build local docker containers, push them to ECR, and start the Fargate services.

For full detailed parameters, prerequisites, and raw AWS CLI commands, see [infra/cloudformation/README.md](file:///c:/workspace/CCCTTNS/Hays_resume_formatter_agent/infra/cloudformation/README.md).

### Quick Deployment Examples

#### 1. Deploy all resources and services:
```powershell
.\scripts\deploy-aws.ps1 -Action DeployAll -DBPassword "YourSecurePassword123!"
```

#### 2. Scale services up or down (0 or 1 tasks):
```powershell
# Scale worker down to 0 (stop)
.\scripts\deploy-aws.ps1 -Action Scale -ServiceToScale worker -DesiredCount 0

# Scale worker up to 1 (run)
.\scripts\deploy-aws.ps1 -Action Scale -ServiceToScale worker -DesiredCount 1

# Scale api down to 0
.\scripts\deploy-aws.ps1 -Action Scale -ServiceToScale api -DesiredCount 0
```

AWS runtime variables used by docker compose:

- `CLOUD_PROVIDER=aws`
- `RUNTIME_MODE=aws`
- `PROCESSING_MODE=async`
- `QUEUE_PROVIDER=sqs`
- `STORAGE_PROVIDER=s3`
- `AGENT_PROVIDER=python_orchestrated`
- `KNOWLEDGE_PROVIDER=bedrock_kb`
- `LLM_BACKEND=aws_bedrock`
- `AWS_REGION=ap-south-1`
- `AWS_PROFILE=default`
- `S3_BUCKET_INPUT` and `S3_BUCKET_OUTPUT`
- `SQS_PROCESSING_QUEUE_URL` (or explicit `SQS_TEMPLATE_ANALYSIS_QUEUE_URL` and `SQS_RESUME_FORMAT_QUEUE_URL`)
- `DATABASE_URL`
- `BEDROCK_KB_ID` (optional)
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` (optional if using mounted profile)

## Run locally with containers (using AWS services)

To rebuild and start the services cleanly:

```powershell
docker compose -f docker-compose.local.yml down
docker compose -f docker-compose.local.yml up --build -d
```

To inspect the logs and confirm the active template analysis pipeline version fingerprint:

```powershell
docker compose -f docker-compose.local.yml logs worker --tail=100
```

Verify that the logs contain:
`[TemplateAnalysis] pipeline_version=layout_v2_agentic_qc_2026_05_28`

This runs API and worker locally while using AWS S3, SQS, RDS, and Bedrock per `.env`.
The local directory is mounted as a volume so that host code changes are instantly reflected without requiring image rebuilds.

## Quick start without containers (optional)

1. Create a virtual environment.
2. Install dependencies.
3. Run API and worker in separate terminals.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH = "$PWD"
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

Worker terminal:

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "$PWD"
python -m src.worker.main
```

## Demo extraction flow

Run template extraction demo against local API:

```powershell
python scripts/demo_extract.py --base-url http://localhost:8000 --template SampleData/templates/template_1_Software_Engineer.docx
```

What this demo shows:

1. Upload template to API.
2. Worker extracts DOCX content and placeholders.
3. Worker builds system/user prompts from Jinja2 templates in `prompts/` and calls Bedrock via Agentic Core.
4. Worker stores field manifest in repository (RDS in AWS mode).
5. Script prints manifest field summary.

## Basic API flow test

1. Upload a DOCX template to `POST /admin/templates`.
2. Poll `GET /jobs/{analysis_job_id}` until `completed`.
3. Submit `POST /format` with `template_id` and `resume_text`.
4. Poll `GET /jobs/{job_id}` and read output key from response.
