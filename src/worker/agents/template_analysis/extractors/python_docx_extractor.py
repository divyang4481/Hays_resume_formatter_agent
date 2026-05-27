from __future__ import annotations

from io import BytesIO
import re
from typing import Any

from docx import Document

TOKEN_RE = re.compile(r"\[[^\]]+\]|\"[^\"]+\"")


def _is_heading(text: str, style_name: str) -> bool:
    return bool(text.strip()) and ("heading" in (style_name or "").lower() or text.isupper())


def _iter_tokens(text: str) -> list[str]:
    return [m.group(0).strip() for m in TOKEN_RE.finditer(text or "")]


def extract_python_docx_evidence(docx_bytes: bytes) -> dict[str, Any]:
    return {"source": "python_docx", "blocks": [], "warnings": []}
