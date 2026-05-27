from __future__ import annotations

from io import BytesIO
import re
from zipfile import ZipFile
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TOKEN_RE = re.compile(r"\[[^\]]+\]|\"[^\"]+\"")
MERGE_RE = re.compile(r"MERGEFIELD\s+([^\s\\]+)", re.IGNORECASE)


def extract_openxml_evidence(docx_bytes: bytes) -> dict:
    blocks = []
    c = 0
    with ZipFile(BytesIO(docx_bytes)) as zf:
        names = [n for n in zf.namelist() if n.startswith("word/") and ("document.xml" in n or "header" in n or "footer" in n or n.endswith("footnotes.xml") or n.endswith("endnotes.xml"))]
        for name in names:
            root = ET.fromstring(zf.read(name))
            for p_idx, p in enumerate(root.iter(f"{W}p")):
                texts = [t.text or "" for t in p.iter(f"{W}t")]
                instr = " ".join((t.text or "") for t in p.iter(f"{W}instrText"))
                full = " ".join(texts).strip()
                tokens = TOKEN_RE.findall(full)
                merge = MERGE_RE.search(instr)
                raw = []
                if merge:
                    raw.append(f"MERGEFIELD {merge.group(1)}")
                raw.extend(tokens)
                for r_idx, tok in enumerate(raw):
                    c += 1
                    blocks.append({
                        "source": "openxml", "block_id": f"ox_b{c:03d}", "location": "header" if "header" in name else "footer" if "footer" in name else "body",
                        "xml_file": name, "container_type": "paragraph", "section_heading": "", "label_text": re.sub(TOKEN_RE, "", full).strip(" :\t"),
                        "placeholder_text": tok if tok.startswith("[") else None, "mergefield_name": merge.group(1) if tok.startswith("MERGEFIELD") and merge else None,
                        "raw_token": tok, "evidence_text": full, "table_index": None, "row_index": None, "cell_index": None,
                        "paragraph_index": p_idx, "run_index": r_idx, "is_bullet": False, "style_name": "", "xml_preview": ET.tostring(p, encoding="unicode")[:300],
                    })
    return {"source": "openxml", "blocks": blocks, "warnings": []}
