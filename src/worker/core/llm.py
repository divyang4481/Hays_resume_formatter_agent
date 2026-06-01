from __future__ import annotations

import json
import re
from typing import Any
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from src.shared.config import settings
from src.worker.core.prompt_manager import PromptManager


class LLMClient:
    def __init__(self) -> None:
        self.provider = "bedrock"
        self.fast_model = settings.llm_model_fast
        self.strong_model = settings.llm_model_strong

        botocore_cfg = Config(
            connect_timeout=settings.bedrock_connect_timeout_seconds,
            read_timeout=settings.bedrock_read_timeout_seconds,
            retries={"max_attempts": settings.bedrock_max_retries, "mode": "standard"},
        )

        session = boto3.Session(profile_name=settings.aws_profile) if settings.aws_profile else boto3.Session()
        self._bedrock_runtime = session.client("bedrock-runtime", region_name=settings.aws_region, config=botocore_cfg)
        self._bedrock_agent_runtime = session.client("bedrock-agent-runtime", region_name=settings.aws_region, config=botocore_cfg)
        self.bedrock_agent_id = settings.bedrock_agent_id
        self.bedrock_agent_alias_id = settings.bedrock_agent_alias_id
        self._bedrock_agent_available = bool(self.bedrock_agent_id and self.bedrock_agent_alias_id)
        self.prompt_manager = PromptManager()

    def extract_structured_fields(self, prompt: str, use_strong_model: bool = False) -> dict:
        model = self.strong_model if use_strong_model else self.fast_model
        text = self._call_bedrock(
            system_prompt="",
            user_prompt=prompt,
            model=model,
            max_tokens=settings.bedrock_max_output_tokens_default,
        )
        return {
            "model": model,
            "provider": self.provider,
            "raw_prompt_size": len(prompt),
            "text": text,
        }

    def _compose_field_search_hint(self, field: dict[str, Any]) -> str:
        """Create a generic search hint from manifest metadata without field-specific rules."""
        candidates: list[str] = []

        for key in ("display_label", "source_hint", "template_token", "formatting_hint"):
            value = field.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())

        aliases = field.get("aliases")
        if isinstance(aliases, list):
            for alias in aliases:
                if isinstance(alias, str) and alias.strip():
                    candidates.append(alias.strip())

        extraction_contract = field.get("extraction_contract")
        if isinstance(extraction_contract, dict):
            mapping_hint = extraction_contract.get("mapping_hint")
            if isinstance(mapping_hint, str) and mapping_hint.strip():
                candidates.append(mapping_hint.strip())

        semantic_contract = field.get("semantic_contract")
        if isinstance(semantic_contract, dict):
            search_intent = semantic_contract.get("resume_search_intent")
            if isinstance(search_intent, str) and search_intent.strip():
                candidates.append(search_intent.strip())

        template_evidence = field.get("template_evidence")
        if isinstance(template_evidence, dict):
            for key in ("section_heading", "region_name", "region_type"):
                value = template_evidence.get(key)
                if isinstance(value, str) and value.strip():
                    candidates.append(value.strip())

        render_contract = field.get("render_contract")
        if isinstance(render_contract, dict):
            anchor_token = render_contract.get("anchor_token")
            if isinstance(anchor_token, str) and anchor_token.strip():
                candidates.append(anchor_token.strip())

            block_tokens = render_contract.get("block_tokens")
            if isinstance(block_tokens, dict):
                for token in block_tokens.values():
                    if isinstance(token, str) and token.strip():
                        candidates.append(token.strip())

        sub_fields = field.get("sub_fields")
        if isinstance(sub_fields, list):
            for sub in sub_fields:
                if not isinstance(sub, dict):
                    continue
                sub_name = sub.get("name")
                if isinstance(sub_name, str) and sub_name.strip():
                    candidates.append(sub_name.strip())
                sub_token = sub.get("template_token")
                if isinstance(sub_token, str) and sub_token.strip():
                    candidates.append(sub_token.strip())

        # Add generic resume heading synonyms for semantic families inferred from field metadata.
        semantic_probe = " ".join(
            str(field.get(k) or "") for k in ("name", "display_label", "source_hint")
        ).lower()
        if any(term in semantic_probe for term in ("qualif", "certif", "accredit", "license", "licence")):
            candidates.extend([
                "Certification",
                "Certifications",
                "Certificate",
                "Professional qualifications",
                "Licenses",
                "Accreditations",
            ])

        unique: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            key = re.sub(r"\s+", " ", item).strip().lower()
            if key and key not in seen:
                seen.add(key)
                unique.append(item)

        return " | ".join(unique[:10])

    def _enrich_fields_for_resume_extraction(self, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
        enriched: list[dict[str, Any]] = []
        for field in fields:
            if not isinstance(field, dict):
                continue
            cloned = dict(field)
            existing_hint = cloned.get("search_hint")
            if not (isinstance(existing_hint, str) and existing_hint.strip()):
                cloned["search_hint"] = self._compose_field_search_hint(cloned)
            enriched.append(cloned)
        return enriched

    def infer_template_fields(
        self,
        *,
        template_name: str,
        tokens: list[dict[str, str]],
        template_text: str,
        use_strong_model: bool = False,
    ) -> list[dict[str, Any]]:
        model = self.strong_model if use_strong_model else self.fast_model

        from src.worker.core.llm_call_manager import llm_call_manager
        
        # Step 1: Layout Planning Agent
        print(f"[PlanAgentPattern] Step 1: Reconstructing and planning layout for {template_name}...")
        layout_plan = llm_call_manager.execute_call(
            llm_client=self,
            namespace="template_analysis",
            context={
                "template_name": template_name,
                "tokens_json": json.dumps(tokens, ensure_ascii=True),
                "template_text_preview": template_text[:6000],
            },
            model=model,
            max_tokens=min(settings.bedrock_max_output_tokens_template_analysis, 4096),
            temperature=0.2, # slightly creative for layout planning structure
            system_template="layout_planner_system.j2",
            user_template="layout_planner_user.j2",
        )
        print(f"[PlanAgentPattern] Step 1 Layout Plan generated (length: {len(layout_plan)} chars).")

        # Step 2: Manifest Generation Agent
        print(f"[PlanAgentPattern] Step 2: Generating final strict JSON manifest for {template_name}...")
        text = llm_call_manager.execute_call(
            llm_client=self,
            namespace="template_analysis",
            context={
                "template_name": template_name,
                "layout_plan": layout_plan,
                "tokens_json": json.dumps(tokens, ensure_ascii=True),
                "template_text_preview": template_text[:6000],
            },
            model=model,
            max_tokens=settings.bedrock_max_output_tokens_template_analysis,
            temperature=settings.bedrock_temperature_template_analysis,
            system_template="template_analysis_system.j2",
            user_template="template_analysis_user.j2",
        )

        import re
        cleaned_text = text.strip()
        markdown_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", cleaned_text)
        if markdown_match:
            cleaned_text = markdown_match.group(1).strip()

        payload = json.loads(cleaned_text)
        fields = payload.get("fields", [])
        if not isinstance(fields, list):
            raise ValueError("Invalid Bedrock payload: 'fields' is not a list")
        return fields


    def plan_manifest_from_evidence(
        self,
        *,
        template_name: str,
        canonical_blocks: list[dict[str, Any]],
        field_candidates: list[dict[str, Any]],
        repeat_groups: list[dict[str, Any]],
        use_strong_model: bool = True,
    ) -> dict[str, Any]:
        model = self.strong_model if use_strong_model else self.fast_model
        
        from src.worker.core.llm_call_manager import llm_call_manager
        import re
        
        candidates_input = []
        for c in field_candidates:
            candidates_input.append({
                "candidate_id": c.get("candidate_id"),
                "suggested_name": c.get("suggested_name"),
                "display_label": c.get("display_label"),
                "field_type": c.get("field_type", "scalar"),
                "template_token": c.get("template_token"),
                "source_block_ids": c.get("source_block_ids", []),
                "template_evidence": c.get("template_evidence", {}),
                "render_contract": c.get("render_contract", {}),
            })
            
        try:
            print(f"[PlanManifest] Planning and standardizing manifest fields for {template_name} using LLM...")
            text = llm_call_manager.execute_call(
                llm_client=self,
                namespace="template_analysis",
                context={
                    "template_name": template_name,
                    "candidates_json": json.dumps(candidates_input, ensure_ascii=True),
                },
                model=model,
                max_tokens=settings.bedrock_max_output_tokens_template_analysis,
                temperature=settings.bedrock_temperature_template_analysis,
                system_template="plan_manifest_system.j2",
                user_template="plan_manifest_user.j2",
            )
            
            cleaned_text = text.strip()
            markdown_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", cleaned_text)
            if markdown_match:
                cleaned_text = markdown_match.group(1).strip()
                
            payload = json.loads(cleaned_text)
            fields = payload.get("fields", [])
            if isinstance(fields, list):
                # Ensure all required fields have their render_contract and source_block_ids preserved
                # from the original candidate matching by name/token if missing
                candidate_map = {c["suggested_name"]: c for c in candidates_input}
                for f in fields:
                    if "source_block_ids" not in f or not f["source_block_ids"]:
                        orig = candidate_map.get(f["name"])
                        if orig:
                            f["source_block_ids"] = orig.get("source_block_ids", [])
                            f["template_token"] = f.get("template_token") or orig.get("template_token")
                            f["template_evidence"] = f.get("template_evidence") or orig.get("template_evidence")
                            f["render_contract"] = f.get("render_contract") or orig.get("render_contract")
                    
                    if "source_classification" not in f:
                        f["source_classification"] = "recruiter_input"
                return {"fields": fields}
        except Exception as e:
            print(f"[PlanManifest] LLM planning failed: {e}. Using deterministic programmatic planner fallback.")
            
        # 100% Generic dynamic pass-through fallback (no hardcoding of any specific field names or mappings)
        fields = []
        for c in field_candidates:
            name = c.get("suggested_name", "")
            fields.append({
                "name": name,
                "display_label": c.get("display_label"),
                "field_type": c.get("field_type", "scalar"),
                "source_classification": "recruiter_input",
                "template_token": c.get("template_token"),
                "source_block_ids": c.get("source_block_ids", []),
                "template_evidence": c.get("template_evidence", {}),
                "render_contract": c.get("render_contract", {}),
            })
        return {"fields": fields}

    def extract_resume_fields(
        self,
        *,
        fields: list[dict[str, Any]],
        resume_text: str,
        use_strong_model: bool = False,
    ) -> dict[str, Any]:
        model = self.strong_model if use_strong_model else self.fast_model
        enriched_fields = self._enrich_fields_for_resume_extraction(fields)

        from src.worker.core.llm_call_manager import llm_call_manager
        text = llm_call_manager.execute_call(
            llm_client=self,
            namespace="resume_extraction",
            context={
                "fields_json": json.dumps(enriched_fields, ensure_ascii=True),
                "resume_text": resume_text,
            },
            model=model,
            max_tokens=settings.bedrock_max_output_tokens_data_mapping,
            temperature=settings.bedrock_temperature_data_mapping,
        )

        import re
        cleaned_text = text.strip()
        markdown_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", cleaned_text)
        if markdown_match:
            cleaned_text = markdown_match.group(1).strip()

        try:
            # Clean common JSON syntax errors produced by LLMs
            repaired = cleaned_text
            # Fix trailing quotes after closing square bracket, e.g. ]" or ]"} or ]"}],"education"
            repaired = re.sub(r'\]\s*"\s*\}', r']}', repaired)
            repaired = re.sub(r'\]\s*"\s*\]', r']]', repaired)
            repaired = re.sub(r'\]\s*"\s*\}\s*\]', r']}]', repaired)
            repaired = re.sub(r'\]\s*"\s*\}\s*(,\s*")', r']}\1', repaired)
            # Fix missing commas between objects in an array: } { -> } , {
            repaired = re.sub(r'\}\s*\{', r'},{', repaired)
            
            payload = json.loads(repaired)
        except Exception as json_err:
            try:
                payload = json.loads(cleaned_text)
            except Exception:
                print(f"Failed to parse LLM response as JSON: {json_err}")
                print("Raw LLM response:")
                print("=" * 80)
                print(text)
                print("=" * 80)
                raise json_err
        if isinstance(payload.get("field_mappings"), dict):
            return payload

        extracted = payload.get("extracted", {})
        if not isinstance(extracted, dict):
            raise ValueError("Invalid Bedrock payload: expected 'field_mappings' or 'extracted'")

        return {
            "field_mappings": {
                k: {
                    "value": v,
                    "confidence": 0.6 if v not in (None, [], "") else 0.0,
                    "status": "mapped" if v not in (None, [], "") else "missing",
                    "source": {"section": None, "evidence_text": None, "page": None},
                }
                for k, v in extracted.items()
            },
            "missing_fields_requiring_recruiter_or_ats_input": [],
        }

    def generate_resume_fields(
        self,
        *,
        fields: list[dict[str, Any]],
        resume_text: str,
        resume_fact_values: dict[str, Any],
        use_strong_model: bool = True,
    ) -> dict[str, Any]:
        model = self.strong_model if use_strong_model else self.fast_model

        from src.worker.core.llm_call_manager import llm_call_manager

        text = llm_call_manager.execute_call(
            llm_client=self,
            namespace="resume_generated",
            context={
                "fields_json": json.dumps(fields, ensure_ascii=True),
                "resume_text": resume_text,
                "resume_fact_values_json": json.dumps(resume_fact_values, ensure_ascii=True),
            },
            model=model,
            max_tokens=settings.bedrock_max_output_tokens_data_mapping,
            temperature=settings.bedrock_temperature_data_mapping,
        )

        cleaned_text = text.strip()
        markdown_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", cleaned_text)
        if markdown_match:
            cleaned_text = markdown_match.group(1).strip()

        try:
            repaired = cleaned_text
            repaired = re.sub(r'\]\s*"\s*\}', r']}', repaired)
            repaired = re.sub(r'\]\s*"\s*\]', r']]', repaired)
            repaired = re.sub(r'\}\s*\{', r'},{', repaired)
            payload = json.loads(repaired)
        except Exception as json_err:
            try:
                payload = json.loads(cleaned_text)
            except Exception:
                print(f"Failed to parse generated-field LLM response as JSON: {json_err}")
                print("Raw generated-field LLM response:")
                print("=" * 80)
                print(text)
                print("=" * 80)
                raise json_err

        if isinstance(payload.get("field_mappings"), dict):
            return payload

        extracted = payload.get("extracted", {})
        if not isinstance(extracted, dict):
            raise ValueError("Invalid Bedrock payload: expected 'field_mappings' or 'extracted'")

        return {
            "field_mappings": {
                k: {
                    "value": v,
                    "confidence": 0.6 if v not in (None, [], "") else 0.0,
                    "status": "mapped" if v not in (None, [], "") else "missing",
                    "source": {"section": None, "evidence_text": None, "page": None},
                }
                for k, v in extracted.items()
            },
            "missing_fields_requiring_recruiter_or_ats_input": [],
        }

    def summarize_resume(
        self,
        *,
        resume_text: str,
        use_strong_model: bool = True,
    ) -> str:
        model = self.strong_model if use_strong_model else self.fast_model

        from src.worker.core.llm_call_manager import llm_call_manager

        # Keep input bounded while preserving enough context for a strong summary.
        bounded_text = resume_text[:24000]
        text = llm_call_manager.execute_call(
            llm_client=self,
            namespace="resume_summary",
            context={"resume_text": bounded_text},
            model=model,
            max_tokens=512,
            temperature=0.1,
        )

        cleaned_text = text.strip()
        markdown_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", cleaned_text)
        if markdown_match:
            cleaned_text = markdown_match.group(1).strip()

        summary = ""
        try:
            payload = json.loads(cleaned_text)
            summary = (
                payload.get("summary")
                or payload.get("resume_summary")
                or payload.get("profile_summary")
                or ""
            )
        except Exception:
            summary = cleaned_text

        summary = re.sub(r"\s+", " ", str(summary)).strip()
        if len(summary) > 500:
            summary = summary[:497].rstrip() + "..."
        return summary

    def _call_bedrock(self, *, system_prompt: str, user_prompt: str, model: str, max_tokens: int, temperature: float = 0.1) -> str:
        text, _ = self._call_bedrock_with_usage(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return text

    def _call_bedrock_with_usage(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> tuple[str, dict[str, int]]:
        usage = {"input_tokens": 0, "output_tokens": 0}
        if self._bedrock_agent_available:
            try:
                text = self._call_bedrock_agent(system_prompt=system_prompt, user_prompt=user_prompt)
                return text, usage
            except ClientError as e:
                error_code = (e.response or {}).get("Error", {}).get("Code", "")
                if error_code == "accessDeniedException":
                    # Disable agent path after first permission failure to avoid repeated latency.
                    self._bedrock_agent_available = False
                    print(
                        "Bedrock Agent access denied. Disabling agent invocation for this worker process "
                        "and falling back to foundation model direct calls."
                    )
                else:
                    print(f"Bedrock Agent invocation failed: {e}. Falling back to foundation model direct call...")
            except Exception as e:
                print(f"Bedrock Agent invocation failed: {e}. Falling back to foundation model direct call...")

        try:
            return self._converse_with_usage(
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as e:
            message = str(e).lower()
            fallback_model = settings.bedrock_fallback_model_id
            if "read timeout" in message and fallback_model and fallback_model != model:
                print(
                    f"Bedrock converse timed out for model {model}. Retrying once with fallback model {fallback_model}."
                )
                return self._converse_with_usage(
                    model=fallback_model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            print(f"Bedrock converse call failed for model {model}: {e}")
            raise e

    def _converse_with_usage(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> tuple[str, dict[str, int]]:
        messages = [
            {
                "role": "user",
                "content": [{"text": user_prompt}]
            }
        ]
        
        system = [{"text": system_prompt}] if system_prompt else []
        
        converse_params = {
            "modelId": model,
            "messages": messages,
            "inferenceConfig": {
                "temperature": temperature,
                "maxTokens": max_tokens
            }
        }
        if system:
            converse_params["system"] = system

        response = self._bedrock_runtime.converse(**converse_params)
        text = response['output']['message']['content'][0]['text']
        usage_info = response.get("usage", {})
        usage = {
            "input_tokens": usage_info.get("inputTokens", 0),
            "output_tokens": usage_info.get("outputTokens", 0)
        }
        return text, usage

    def _call_bedrock_agent(self, *, system_prompt: str, user_prompt: str) -> str:
        prompt = f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}"
        response = self._bedrock_agent_runtime.invoke_agent(
            agentId=self.bedrock_agent_id,
            agentAliasId=self.bedrock_agent_alias_id,
            sessionId=f"resume-{uuid4()}",
            inputText=prompt,
        )

        parts: list[str] = []
        for event in response.get("completion", []):
            chunk = event.get("chunk")
            if not chunk:
                continue
            data = chunk.get("bytes", b"")
            if isinstance(data, (bytes, bytearray)):
                parts.append(data.decode("utf-8", errors="ignore"))
        return "".join(parts).strip()
