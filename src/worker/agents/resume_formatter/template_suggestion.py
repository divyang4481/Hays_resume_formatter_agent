from __future__ import annotations


class TemplateSuggestionService:
    @staticmethod
    def suggest_templates(resume_text: str) -> list[dict]:
        """
        Suggest matching templates for the given resume text.
        Returns an empty list for now (to be integrated with vector/repository search in the future).
        """
        return []
