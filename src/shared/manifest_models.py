from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

FieldType = Literal["scalar", "array", "object", "array_object", "copy_paste_block"]
SourceClassification = Literal["resume_fact", "generated", "input_only", "recruiter_input", "ats_input"]
RenderStrategy = Literal[
    "mergefield_replace",
    "placeholder_replace",
    "bullet_list_replace",
    "repeat_block",
    "copy_paste_block",
    "remove_instruction_block",
    "remove_empty_block",
]


class SemanticContract(BaseModel):
    business_meaning: str = ""
    resume_search_intent: str = ""
    acceptable_sources: list[str] = Field(default_factory=list)
    do_not_infer: list[str] = Field(default_factory=list)


class ExtractionContract(BaseModel):
    llm_output_key: str = ""
    value_shape: str = "string"
    evidence_required: bool = True
    mapping_hint: str = ""


class RenderContract(BaseModel):
    render_strategy: RenderStrategy = "placeholder_replace"
    anchor_token: str = ""
    formatting: dict[str, Any] = Field(default_factory=dict)
    block_tokens: dict[str, str] = Field(default_factory=dict)
    empty_value_policy: str = "remove_placeholder"
    occurrence_selector: dict[str, Any] = Field(default_factory=dict)
    repeat_items: list[dict[str, str]] = Field(default_factory=list)


class ValidationContract(BaseModel):
    required: bool = False
    min_confidence: float = 0.0
    missing_policy: str = "allow_missing"


class SubFieldContract(BaseModel):
    name: str
    field_type: FieldType = "scalar"
    template_token: str = ""


class TemplateFieldV2(BaseModel):
    name: str
    display_label: str = ""
    aliases: list[str] = Field(default_factory=list)
    field_type: FieldType
    required: bool = False
    source_classification: SourceClassification = "resume_fact"
    semantic_contract: SemanticContract = Field(default_factory=SemanticContract)
    extraction_contract: ExtractionContract = Field(default_factory=ExtractionContract)
    render_contract: RenderContract = Field(default_factory=RenderContract)
    validation_contract: ValidationContract = Field(default_factory=ValidationContract)
    sub_fields: list[SubFieldContract] = Field(default_factory=list)
    source_hint: str = ""
    template_token: str = ""
    formatting_hint: str = ""
    injection_details: dict[str, Any] = Field(default_factory=dict)
    source_block_ids: list[str] = Field(default_factory=list)
    template_evidence: dict[str, Any] = Field(default_factory=dict)
    occurrence_selector: dict[str, Any] = Field(default_factory=dict)
    repeat_items: list[dict[str, str]] = Field(default_factory=list)


class TemplateManifestV2(BaseModel):
    version: int = 2
    manifest_schema: str = "template_manifest_v2"
    template_id: str | None = None
    manifest_id: str | None = None
    fields: list[TemplateFieldV2] = Field(default_factory=list)
    layout: dict[str, Any] = Field(default_factory=dict)


class FieldMappingEvidence(BaseModel):
    section: str | None = None
    evidence_text: str | None = None
    page: int | None = None


class FieldMappingValue(BaseModel):
    value: Any = None
    confidence: float = 0.0
    status: str = "missing"
    source: FieldMappingEvidence = Field(default_factory=FieldMappingEvidence)


class ResumeMappingResult(BaseModel):
    field_mappings: dict[str, FieldMappingValue] = Field(default_factory=dict)
    missing_fields_requiring_recruiter_or_ats_input: list[str] = Field(default_factory=list)


class FilledTemplatePayload(BaseModel):
    template_id: str | None = None
    manifest_id: str | None = None
    render_values: dict[str, Any] = Field(default_factory=dict)
    placeholder_values: dict[str, Any] | list[dict[str, Any]] = Field(default_factory=dict)
    repeat_blocks: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    missing_fields_requiring_recruiter_or_ats_input: list[str] = Field(default_factory=list)


def adapt_v1_field_to_v2(field: dict[str, Any]) -> dict[str, Any]:
    token = field.get("template_token") or field.get("token") or ""
    return TemplateFieldV2(
        name=field.get("name", ""),
        field_type=field.get("field_type", field.get("type", "scalar")),
        required=bool(field.get("required", False)),
        source_classification=field.get("source_classification", "resume_fact"),
        source_hint=field.get("source_hint", ""),
        template_token=token,
        formatting_hint=field.get("formatting_hint", ""),
        extraction_contract=ExtractionContract(llm_output_key=field.get("name", "")),
        render_contract=RenderContract(anchor_token=token),
        validation_contract=ValidationContract(required=bool(field.get("required", False))),
        injection_details=field.get("injection_details", {}),
    ).model_dump()
