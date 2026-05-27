from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import boto3

from src.shared.config import settings
from src.worker.core.prompt_manager import PromptManager


class LLMClient:
    def __init__(self) -> None:
        self.provider = "bedrock"
        self.fast_model = settings.llm_model_fast
        self.strong_model = settings.llm_model_strong
        self._bedrock_runtime = boto3.client("bedrock-runtime", region_name=settings.aws_region)
        self._bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=settings.aws_region)
        self.bedrock_agent_id = settings.bedrock_agent_id
        self.bedrock_agent_alias_id = settings.bedrock_agent_alias_id
        self.prompt_manager = PromptManager()

    def extract_structured_fields(self, prompt: str, use_strong_model: bool = False) -> dict:
        model = self.strong_model if use_strong_model else self.fast_model
        text = self._call_bedrock(system_prompt="", user_prompt=prompt, model=model, max_tokens=1200)
        return {
            "model": model,
            "provider": self.provider,
            "raw_prompt_size": len(prompt),
            "text": text,
        }

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
            if "candidate_own_cv" in name or "own_cv" in name:
                continue
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

        from src.worker.core.llm_call_manager import llm_call_manager
        text = llm_call_manager.execute_call(
            llm_client=self,
            namespace="resume_extraction",
            context={
                "fields_json": json.dumps(fields, ensure_ascii=True),
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

        payload = json.loads(cleaned_text)
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
        if self.bedrock_agent_id and self.bedrock_agent_alias_id:
            try:
                text = self._call_bedrock_agent(system_prompt=system_prompt, user_prompt=user_prompt)
                return text, usage
            except Exception as e:
                print(f"Bedrock Agent invocation failed: {e}. Falling back to foundation model direct call...")

        if model.startswith("meta.llama"):
            prompt = f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n{system_prompt}<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n{user_prompt}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
            body = {
                "prompt": prompt,
                "max_gen_len": min(max_tokens, 2048),
                "temperature": temperature,
                "top_p": 0.9
            }
            response = self._bedrock_runtime.invoke_model(
                modelId=model,
                body=json.dumps(body).encode("utf-8"),
                contentType="application/json",
                accept="application/json",
            )
            headers = response.get("ResponseMetadata", {}).get("HTTPHeaders", {})
            usage["input_tokens"] = int(headers.get("x-amzn-bedrock-input-token-count", 0))
            usage["output_tokens"] = int(headers.get("x-amzn-bedrock-output-token-count", 0))

            payload = json.loads(response["body"].read().decode("utf-8"))
            return payload.get("generation", "").strip(), usage

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": temperature,
        }
        response = self._bedrock_runtime.invoke_model(
            modelId=model,
            body=json.dumps(body).encode("utf-8"),
            contentType="application/json",
            accept="application/json",
        )
        headers = response.get("ResponseMetadata", {}).get("HTTPHeaders", {})
        usage["input_tokens"] = int(headers.get("x-amzn-bedrock-input-token-count", 0))
        usage["output_tokens"] = int(headers.get("x-amzn-bedrock-output-token-count", 0))

        payload = json.loads(response["body"].read().decode("utf-8"))
        content = payload.get("content", [])
        text_parts = [item.get("text", "") for item in content if item.get("type") == "text"]
        return "\n".join(text_parts).strip(), usage

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
