from __future__ import annotations
from src.shared.repository import repo


class TemplateSuggestionService:
    @staticmethod
    def suggest_templates(resume_text: str) -> list[dict]:
        """
        Suggest matching templates for the given resume text.
        Queries the database dynamically and ranks them based on content mapping.
        """
        if not resume_text:
            return []

        try:
            total, templates = repo.list_templates(limit=100)
        except Exception as e:
            print(f"[TemplateSuggestion] Failed to list templates from repo: {e}")
            return []

        if not templates:
            return []

        text_lower = resume_text.lower()

        # Keyword sets
        tech_keywords = {
            "software", "developer", "cloud", "aws", "azure", "gcp", "engineer",
            "java", "python", "programming", "architect", "data science", "machine learning",
            "ml", "ai", "kubernetes", "docker", "devops", "microservices", "solutions architect"
        }
        finance_keywords = {
            "tax", "vat", "accounting", "accountant", "audit", "finance", "fiscal",
            "taxation", "wealth", "revenue", "cpa", "audit manager", "hmrc"
        }

        # Count occurrences
        tech_matches = sum(1 for kw in tech_keywords if kw in text_lower)
        finance_matches = sum(1 for kw in finance_keywords if kw in text_lower)

        suggestions = []
        for tpl in templates:
            tpl_id = tpl["template_id"]
            tpl_name = tpl["template_name"]
            tpl_name_lower = tpl_name.lower()

            score = 0.70  # Baseline
            reason = "Fits standard corporate layout for general professional experience."

            # Category-based heuristics
            if "tax" in tpl_name_lower or "finance" in tpl_name_lower or "accounting" in tpl_name_lower:
                if finance_matches > 0:
                    score = min(0.95, 0.85 + (0.05 * min(finance_matches, 2)))
                    reason = f"Excellent match! Found key finance/tax terms ('{', '.join([kw for kw in finance_keywords if kw in text_lower][:2])}') in candidate resume."
                elif tech_matches > 3:
                    score = 0.40  # Poor fit for tech candidates
                    reason = "Low match: Technical profiles are generally not suited for tax-specific formatting templates."
                else:
                    score = 0.55
                    reason = "Medium match: Recommended for finance and accounting roles."
            elif "tech" in tpl_name_lower or "it " in tpl_name_lower or "developer" in tpl_name_lower or "engineer" in tpl_name_lower:
                if tech_matches > 0:
                    score = min(0.95, 0.85 + (0.03 * min(tech_matches, 3)))
                    reason = f"Highly Recommended! Profile matches multiple cloud & software terms ('{', '.join([kw for kw in tech_keywords if kw in text_lower][:2])}')."
                else:
                    score = 0.50
                    reason = "Medium match: Optimized for IT, cloud engineering, and technical layouts."
            elif "worldwide" in tpl_name_lower or "global" in tpl_name_lower or "international" in tpl_name_lower:
                if tech_matches > 2:
                    score = min(0.95, 0.88 + (0.02 * min(tech_matches, 3)))
                    reason = "Excellent match! Standard Hays global formatting optimized for high-impact technical resumes."
                else:
                    score = 0.82
                    reason = "Highly recommended standard worldwide format for executive and professional candidate CVs."
            else:
                # Generic fallback templates
                if tech_matches > 2:
                    score = 0.80
                    reason = "Strong standard layout suitable for professional technical candidates."
                else:
                    score = 0.75
                    reason = "Good standard layout for presenting candidate achievements clearly."

            suggestions.append({
                "template_id": tpl_id,
                "template_name": tpl_name,
                "match_score": round(score * 100),
                "reason": reason
            })

        # Sort descending by match score
        suggestions.sort(key=lambda x: x["match_score"], reverse=True)
        return suggestions

