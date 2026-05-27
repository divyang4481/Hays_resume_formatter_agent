# Field Manifest v1

This manifest is produced by template-analysis worker and consumed by resume-format worker.

## Schema

```json
{
  "manifest_id": "uuid",
  "template_id": "uuid",
  "version": 1,
  "created_at": "ISO-8601",
  "fields": [
    {
      "name": "candidate_name",
      "field_type": "scalar|array|array_object",
      "source_hint": "hint to locate value from resume",
      "template_token": "{{candidate_name}}",
      "required": true,
      "formatting_hint": "title_case"
    }
  ]
}
```

## Notes

- `field_type=array_object` is used for experience and education blocks.
- Rendering remains deterministic in MVP.
- LLM is used for semantic inference and extraction only.
