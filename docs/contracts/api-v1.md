# API v1

## Endpoints

- `GET /health`
- `POST /admin/templates` (DOCX upload)
- `POST /format` (submit resume formatting job)
- `GET /jobs/{job_id}`
- `GET /templates/{template_id}/manifest`

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
