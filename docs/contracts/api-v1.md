# API v1

## Endpoints

- `GET /health`
- `POST /admin/templates` (DOCX upload)
- `POST /format` (submit resume formatting job using JSON or multipart resume file upload)
- `GET /jobs/{job_id}`
- `GET /templates/{template_id}/manifest`

## Example: Submit format job with JSON

```json
{
  "template_id": "uuid",
  "resume_text": "John Doe\njohn@doe.com\n..."
}
```

## Example: Submit format job with multipart file upload

`POST /format` also accepts `multipart/form-data` for Swagger UI and browser clients:

- `file`: candidate resume file (`PDF`, `DOCX`, or `TXT`)
- `template_id`: optional template ID
- `resume_text`: optional pasted resume text
- `resume_object_key`: optional existing object-store key

## Response

```json
{
  "job_id": "uuid",
  "status": "queued"
}
```
