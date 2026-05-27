# Queue Messages v1

## TemplateAnalysisMessage

```json
{
  "job_id": "uuid",
  "template_id": "uuid",
  "template_object_key": "templates/name.docx",
  "template_name": "name.docx"
}
```

## ResumeFormatMessage

```json
{
  "job_id": "uuid",
  "template_id": "uuid",
  "resume_text": "optional text",
  "resume_object_key": "optional object key"
}
```

## Processing Rules

- Exactly one of `resume_text` or `resume_object_key` should be provided.
- Failed jobs are marked `failed` and can be retried by re-queue.
- MVP queue implementation is in-memory; swap with SQS adapter for AWS deployment.
