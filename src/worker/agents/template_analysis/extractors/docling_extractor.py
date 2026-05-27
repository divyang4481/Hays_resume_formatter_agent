from __future__ import annotations


def extract_docling_layout_evidence(docx_bytes: bytes, filename: str = "template.docx") -> dict:
    try:
        from docling.document_converter import DocumentConverter  # type: ignore
    except Exception:
        return {"source": "docling", "pages": [], "blocks": [], "warnings": ["docling_not_installed_cpu_fallback"]}

    try:
        conv = DocumentConverter()
        res = conv.convert(filename, source=docx_bytes)
        doc = getattr(res, "document", None)
        blocks = []
        for i, b in enumerate(getattr(doc, "texts", []) or [], start=1):
            blocks.append({"block_id": f"dl_b{i:03d}", "text": str(getattr(b, "text", "")), "page": getattr(b, "page_no", None)})
        return {"source": "docling", "pages": [], "blocks": blocks, "warnings": []}
    except Exception as e:
        return {"source": "docling", "pages": [], "blocks": [], "warnings": [f"docling_parse_error:{e}"]}
