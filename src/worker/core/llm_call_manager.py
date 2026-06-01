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
        return f"{text[:limit]}\n...[truncated {len(text) - limit} chars]"

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

        text, usage = llm_client._call_bedrock_with_usage(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        if settings.llm_log_prompts:
            print("\n[LLMCallManager] ===== LLM PROMPT START =====")
            print(f"[LLMCallManager] namespace={namespace} model={model} temp={temperature} max_tokens={max_tokens}")
            print("[LLMCallManager] --- SYSTEM PROMPT ---")
            print(self._truncate_for_log(system_prompt))
            print("[LLMCallManager] --- USER PROMPT ---")
            print(self._truncate_for_log(user_prompt))
            print("[LLMCallManager] --- MODEL RESPONSE ---")
            print(self._truncate_for_log(text))
            print("[LLMCallManager] ===== LLM PROMPT END =====\n")

        latency = time.time() - start_time

        input_tokens = usage.get("input_tokens") or self.estimate_tokens(system_prompt + user_prompt)
        output_tokens = usage.get("output_tokens") or self.estimate_tokens(text)

        repo.save_llm_call(
            model_id=model,
            prompt_system=system_prompt,
            prompt_user=user_prompt,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_seconds=latency,
        )

        print(
            f"[LLMCallManager] Call recorded: model={model}, "
            f"input_tokens={input_tokens}, output_tokens={output_tokens}, "
            f"latency={latency:.2f}s"
        )
        return text


llm_call_manager = LLMCallManager()
