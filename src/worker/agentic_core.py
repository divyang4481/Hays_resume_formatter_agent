from __future__ import annotations

from src.worker.core.llm import LLMClient


class AgenticCore:
    def __init__(self) -> None:
        self.llm = LLMClient()

    def infer_template_manifest_fields(
        self,
        *,
        template_name: str,
        tokens: list[dict[str, str]],
        template_text: str,
        use_strong_model: bool = False,
    ) -> list[dict]:
        return self.llm.infer_template_fields(
            template_name=template_name,
            tokens=tokens,
            template_text=template_text,
            use_strong_model=use_strong_model,
        )

    def plan_manifest_from_evidence(
        self,
        *,
        template_name: str,
        canonical_blocks: list[dict],
        field_candidates: list[dict],
        repeat_groups: list[dict],
        use_strong_model: bool = True,
    ) -> dict:
        return self.llm.plan_manifest_from_evidence(
            template_name=template_name,
            canonical_blocks=canonical_blocks,
            field_candidates=field_candidates,
            repeat_groups=repeat_groups,
            use_strong_model=use_strong_model,
        )

    def extract_resume_fields(
        self,
        *,
        fields: list[dict],
        resume_text: str,
        use_strong_model: bool = False,
    ) -> dict:
        return self.llm.extract_resume_fields(
            fields=fields,
            resume_text=resume_text,
            use_strong_model=use_strong_model,
        )
