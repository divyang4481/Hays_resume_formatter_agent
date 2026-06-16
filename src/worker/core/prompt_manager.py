from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined


class PromptManager:
    def __init__(self, prompt_roots: list[str] | None = None) -> None:
        if prompt_roots is None:
            prompt_roots = [
                "src/worker/agents/template_analysis/prompts",
                "src/worker/agents/resume_formatter/prompts",
            ]
        
        roots = [Path(root) for root in prompt_roots]
        loader = FileSystemLoader(roots)
        self.env = Environment(loader=loader, undefined=StrictUndefined, autoescape=False)

    def render(self, template_path: str, context: dict[str, Any]) -> str:
        template = self.env.get_template(template_path)
        return template.render(**context)

    def build_system_user_prompts(
        self,
        *,
        namespace: str,
        context: dict[str, Any],
    ) -> tuple[str, str]:
        # Try finding unique names matching {namespace}_system.j2 and {namespace}_user.j2 first:
        try:
            system_prompt = self.render(f"{namespace}_system.j2", context)
        except Exception:
            try:
                system_prompt = self.render(f"{namespace}/system_prompt.j2", context)
            except Exception:
                system_prompt = self.render("system_prompt.j2", context)

        try:
            user_prompt = self.render(f"{namespace}_user.j2", context)
        except Exception:
            try:
                user_prompt = self.render(f"{namespace}/user_prompt.j2", context)
            except Exception:
                user_prompt = self.render("user_prompt.j2", context)

        return system_prompt, user_prompt
