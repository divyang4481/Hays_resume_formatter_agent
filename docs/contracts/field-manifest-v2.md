# Field Manifest v2

`TemplateManifestV2` adds explicit contracts per field:
- semantic_contract
- extraction_contract
- render_contract
- validation_contract

Top-level shape:
```json
{"version":2,"manifest_schema":"template_manifest_v2","fields":[]}
```

v1 compatibility aliases are kept: `source_hint`, `template_token`, `formatting_hint`, `injection_details`.
