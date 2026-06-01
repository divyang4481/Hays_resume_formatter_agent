"""
Deep XML inspection of the rendered DOCX to understand what's actually in
the work experience and education paragraphs, and why skills is duplicating.
"""
import sys, json
from io import BytesIO
from pathlib import Path
from lxml import etree
from docx import Document
from docx.oxml.ns import qn

sys.path.insert(0, '.')

docx_path = Path('formatted_resume_v2.docx')
doc = Document(str(docx_path))

NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

def para_raw_text(p_el):
    """Extract ALL text from a paragraph element including instrText."""
    parts = []
    for t in p_el.findall(f'.//{{{NS}}}t'):
        parts.append(t.text or '')
    return ''.join(parts)

def para_instr_text(p_el):
    """Extract instruction text (inside fields)."""
    parts = []
    for t in p_el.findall(f'.//{{{NS}}}instrText'):
        parts.append(t.text or '')
    return ''.join(parts)

def has_fldchar(p_el):
    return bool(p_el.findall(f'.//{{{NS}}}fldChar'))

def has_fldSimple(p_el):
    return bool(p_el.findall(f'.//{{{NS}}}fldSimple'))

# Scan the body directly
body_el = doc._element.find(f'.//{{{NS}}}body')
all_body_direct = list(body_el)  # direct children

print(f"Total direct body children: {len(all_body_direct)}")
print()

# Count para types
para_count = 0
for child in all_body_direct:
    tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
    raw = para_raw_text(child)
    instr = para_instr_text(child)
    fc = has_fldchar(child)
    
    if tag == 'p':
        display = raw[:80] if raw.strip() else ('[MACROBUTTON]' if fc else '[EMPTY]')
        para_count += 1
        print(f"  [{para_count:03d}] <w:p> text={repr(display[:60])} fldChar={fc}")
    elif tag == 'tbl':
        print(f"  [TBL] <w:tbl>")
    elif tag == 'sectPr':
        print(f"  [END] <w:sectPr>")
    else:
        print(f"  [???] <{tag}>")

print()
print(f"Total direct-body paragraphs: {para_count}")
print()

# Check the skills manifest field
from src.shared.repository import repo
template_id = 'f694b36c-1f5e-4c04-bbdc-ff717e5cbcf8'
m = repo.get_manifest(template_id)
if m:
    for f in m.get('fields', []):
        if f.get('name') == 'skills':
            print("=== SKILLS FIELD ===")
            print(json.dumps(f, indent=2))
            break
