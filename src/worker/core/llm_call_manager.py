from __future__ import annotations

import time
import json
from typing import Any
from src.shared.repository import repo
from src.shared.config import settings
from src.worker.core.prompt_manager import PromptManager


class LLMCallManager:
    def __init__(self) -> None:
        self.prompt_manager = PromptManager()

    def estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    def _truncate_for_log(self, text: str) -> str:
        limit = max(1000, int(settings.llm_log_prompt_chars))
        if len(text) <= limit:
            return text
        return f"{text[:limit]}\n...[truncated {len(text) - limit} chars for log only]"

    def execute_call(
        self,
        *,
        llm_client: Any,
        namespace: str,
        context: dict[str, Any],
        model: str,
        max_tokens: int,
        temperature: float,
        system_template: str | None = None,
        user_template: str | None = None,
        job_id: str | None = None,
    ) -> str:
        if system_template and user_template:
            system_prompt = self.prompt_manager.render(system_template, context)
            user_prompt = self.prompt_manager.render(user_template, context)
        else:
            system_prompt, user_prompt = self.prompt_manager.build_system_user_prompts(
                namespace=namespace,
                context=context,
            )

        start_time = time.time()
        text = ""
        usage: dict[str, int] = {}
        call_error: Exception | None = None

        try:
            text, usage = llm_client._call_bedrock_with_usage(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as e:
            call_error = e

        if settings.llm_log_prompts:
            print("\n[LLMCallManager] ===== LLM PROMPT START =====")
            print(
                f"[LLMCallManager] namespace={namespace} model={model} temp={temperature} max_tokens={max_tokens}"
            )
            print("[LLMCallManager] --- SYSTEM PROMPT ---")
            print(self._truncate_for_log(system_prompt))
            print("[LLMCallManager] --- USER PROMPT ---")
            print(self._truncate_for_log(user_prompt))
            print("[LLMCallManager] --- MODEL RESPONSE ---")
            print(self._truncate_for_log(text))
            if call_error:
                print("[LLMCallManager] --- MODEL ERROR ---")
                print(self._truncate_for_log(str(call_error)))
            print("[LLMCallManager] ===== LLM PROMPT END =====\n")

        latency = time.time() - start_time

        input_tokens = usage.get("input_tokens") or self.estimate_tokens(
            system_prompt + user_prompt
        )
        output_tokens = usage.get("output_tokens") or (
            self.estimate_tokens(text) if text else 0
        )

        prompt_user_for_log = user_prompt
        if call_error:
            prompt_user_for_log = f"{user_prompt}\n\n[LLM_CALL_ERROR] {str(call_error)}"

        from src.shared.repository import active_job_id

        effective_job_id = job_id or context.get("job_id") or active_job_id.get()

        try:
            repo.save_llm_call(
                model_id=model,
                prompt_system=system_prompt,
                prompt_user=prompt_user_for_log,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_seconds=latency,
                job_id=effective_job_id,
            )
            print(
                f"[LLMCallManager] Call recorded: model={model}, "
                f"input_tokens={input_tokens}, output_tokens={output_tokens}, "
                f"latency={latency:.2f}s, success={call_error is None}, "
                f"job_id={effective_job_id}"
            )
        except Exception as log_err:
            print(f"[LLMCallManager] Failed to persist LLM call log: {log_err}")

        if call_error:
            raise call_error
        return text


llm_call_manager = LLMCallManager()
