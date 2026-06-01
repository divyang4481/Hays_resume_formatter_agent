# API v1

## Endpoints

- Browser-facing POC routes are served under `/api` through the frontend proxy.
- `GET /api/health`
- `POST /api/admin/templates` (DOCX upload)
- `POST /api/format` (submit resume formatting job)
- `GET /api/jobs/{job_id}`
- `GET /api/templates/{template_id}/manifest`
- `GET /api/.well-known/agent.json` (agent discovery metadata)
- `GET /api/mcp/manifest` (alias for agent discovery metadata)

## Example: Submit format job

```json
{
  "template_id": "uuid",
  "resume_text": "John Doe\njohn@doe.com\n..."
}
```

## Response

```json
{
  "job_id": "uuid",
  "status": "queued"
}
```
