"""Debug script to verify that the fixed block indexer now sees macrobutton paragraphs."""
import sys
from io import BytesIO
sys.path.insert(0, '.')
from src.shared.repository import repo
from src.shared.storage import object_store
from docx import Document
from docx.oxml.ns import qn

template_id = 'f694b36c-1f5e-4c04-bbdc-ff717e5cbcf8'
template = repo.get_template(template_id)
if not template:
    print('Template not found')
    sys.exit(1)

template_bytes = object_store.get_bytes(template['object_key'])
doc = Document(BytesIO(template_bytes))

body_el = doc._element.find('.//' + qn('w:body'))
all_body_paras = []
if body_el is not None:
    for child in body_el:
        if child.tag != qn('w:p'):
            continue
        texts = [(t.text or '') for t in child.findall('.//' + qn('w:t'))]
        paragraph_text = ''.join(texts).strip()
        has_tokens = bool(
            child.findall('.//' + qn('w:fldSimple')) or
            child.findall('.//' + qn('w:instrText')) or
            child.findall('.//' + qn('w:fldChar'))
        )
        if not (paragraph_text or has_tokens):
            continue
        all_body_paras.append((len(all_body_paras), paragraph_text, has_tokens))

print(f'Total body paras with fix: {len(all_body_paras)}')
for idx, text, has_tok in all_body_paras:
    if 4 <= idx <= 17:
        label = repr(text[:60]) if text else '[MACROBUTTON/FIELD]'
        print(f'  b_{idx:03d}: {label}  has_tokens={has_tok}')
