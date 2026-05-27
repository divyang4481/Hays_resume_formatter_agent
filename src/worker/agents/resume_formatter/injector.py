from __future__ import annotations

import copy
import re
from io import BytesIO
from typing import Any

from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from lxml import etree


def _normalize_field_name(token: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", token.strip()).strip("_").lower()
    return normalized or "unknown_field"


def _serialize_value(value: Any, field_type: str = "scalar") -> str:
    """Convert any extracted field value to a safe string for DOCX injection."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        if len(value) == 0:
            return ""
        first = value[0]
        if isinstance(first, dict):
            parts: list[str] = []
            for item in value:
                row_parts = [str(v) for v in item.values() if v is not None and str(v).strip()]
                parts.append("  ".join(row_parts) if row_parts else "")
            return "\n".join(parts)
        else:
            return "\n".join(str(v) for v in value if v is not None)
    return str(value)


# ---------------------------------------------------------------------------
# Injection Strategy 1: Word Mail Merge MERGEFIELD (XML level)
# ---------------------------------------------------------------------------

def _inject_mergefields_in_element(para_elem: Any, field_map: dict[str, str]) -> None:
    """Helper to inject both complex (w:fldChar) and simple (w:fldSimple) merge fields in a paragraph element."""
    # 1. Complex fields (w:fldChar)
    runs = para_elem.findall(".//" + qn("w:r"))
    state: str | None = None     # None | "in_field" | "in_display"
    current_field: str | None = None
    display_runs: list[Any] = []

    for run in runs:
        fld_char = run.find(qn("w:fldChar"))
        instr_text = run.find(qn("w:instrText"))

        if fld_char is not None:
            fld_type = fld_char.get(qn("w:fldCharType"))
            if fld_type == "begin":
                state = "in_field"
                current_field = None
                display_runs = []
            elif fld_type == "separate":
                state = "in_display"
                display_runs = []
            elif fld_type == "end":
                if current_field and current_field in field_map and display_runs:
                    value = field_map[current_field]
                    t = display_runs[0].find(qn("w:t"))
                    if t is None:
                        t = etree.SubElement(display_runs[0], qn("w:t"))
                    t.text = value
                    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                    for dr in display_runs[1:]:
                        t2 = dr.find(qn("w:t"))
                        if t2 is not None:
                            t2.text = ""
                state = None
                current_field = None
                display_runs = []

        elif instr_text is not None and state == "in_field":
            text = (instr_text.text or "").strip()
            m = re.search(r"MERGEFIELD\s+(\S+)", text, re.IGNORECASE)
            if m:
                current_field = m.group(1)

        elif state == "in_display":
            t = run.find(qn("w:t"))
            if t is not None:
                display_runs.append(run)

    # 2. Simple fields (w:fldSimple)
    fld_simples = para_elem.findall(".//" + qn("w:fldSimple"))
    for fld in fld_simples:
        instr = fld.get(qn("w:instr")) or ""
        m = re.search(r"MERGEFIELD\s+(\S+)", instr, re.IGNORECASE)
        if m:
            mf_name = m.group(1).strip()
            if mf_name in field_map:
                value = field_map[mf_name]
                texts = fld.findall(".//" + qn("w:t"))
                if texts:
                    texts[0].text = value
                    texts[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                    for t in texts[1:]:
                        t.text = ""
                else:
                    r = etree.SubElement(fld, qn("w:r"))
                    t = etree.SubElement(r, qn("w:t"))
                    t.text = value
                    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def _row_contains_tablestart(tr_elem: Any, table_name: str) -> bool:
    for instr in tr_elem.findall(".//" + qn("w:instrText")):
        if f"TableStart:{table_name}" in (instr.text or ""):
            return True
    for fld in tr_elem.findall(".//" + qn("w:fldSimple")):
        instr = fld.get(qn("w:instr")) or ""
        if f"TableStart:{table_name}" in instr:
            return True
    return False


def _inject_table_merge_rows(doc: Document, table_data_map: dict[str, list[dict[str, str]]]) -> None:
    """Scan all tables in the document and expand rows matching TableStart:<table_name> / TableEnd:<table_name> markers."""
    if not table_data_map:
        return

    for table in doc.tables:
        i = 0
        while i < len(table.rows):
            row = table.rows[i]
            tr_elem = row._tr
            
            matched_table_name = None
            for tname in table_data_map.keys():
                if _row_contains_tablestart(tr_elem, tname):
                    matched_table_name = tname
                    break
            
            if matched_table_name:
                items = table_data_map[matched_table_name]
                tr_parent = tr_elem.getparent()
                tr_index = tr_parent.index(tr_elem)
                
                # Clone and inject for each item in the list
                for item in items:
                    cloned_tr = copy.deepcopy(tr_elem)
                    
                    local_field_map = {
                        f"TableStart:{matched_table_name}": "",
                        f"TableEnd:{matched_table_name}": "",
                        **item
                    }
                    
                    # Also map lowercase/stripped keys for reliability
                    for k, v in list(local_field_map.items()):
                        local_field_map[k.lower()] = v
                        local_field_map[k.strip()] = v
                    
                    for para_p in cloned_tr.findall(".//" + qn("w:p")):
                        _inject_mergefields_in_element(para_p, local_field_map)
                    
                    # Insert the cloned row
                    tr_parent.insert(tr_index, cloned_tr)
                    tr_index += 1
                
                # Remove the original template row
                tr_parent.remove(tr_elem)
                # Adjust loop index over the newly inserted rows
                i += len(items)
            else:
                i += 1


def _inject_mergefields(doc: Document, field_map: dict[str, str]) -> None:
    """Replace Word MERGEFIELD values (both simple and complex) at the XML element level."""
    if not field_map:
        return

    def _process_container(container: Any) -> None:
        for para in container.paragraphs:
            _inject_mergefields_in_element(para._element, field_map)
        for table in container.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        _inject_mergefields_in_element(para._element, field_map)

    _process_container(doc)
    for section in doc.sections:
        if section.header:
            _process_container(section.header)
        if section.footer:
            _process_container(section.footer)

    print(f"[MergeField] Applied XML-level replacement for {len(field_map)} fields: {list(field_map.keys())}")


# ---------------------------------------------------------------------------
# Injection Strategy 2: Text placeholder replacement (Macrobutton aware)
# ---------------------------------------------------------------------------

def _replace_in_paragraph(paragraph: Any, key: str, value: str) -> bool:
    """Replace a text placeholder in a paragraph. Returns True if replaced."""
    if key not in paragraph.text:
        return False

    # Fast path: placeholder fully in one run
    for run in paragraph.runs:
        if key in run.text:
            run.text = run.text.replace(key, value)
            return True

    # Slow path: placeholder split across runs — merge then redistribute
    if paragraph.runs:
        full_text = "".join(run.text for run in paragraph.runs)
        if key in full_text:
            new_text = full_text.replace(key, value)
            paragraph.runs[0].text = new_text
            for run in paragraph.runs[1:]:
                run.text = ""
            return True
    return False


def _paragraph_contains_token(para: Any, token: str) -> bool:
    """Check if a paragraph contains a token, either in plain text or inside a macrobutton instruction."""
    if token in para.text:
        return True
    p_elem = para._element
    for instr in p_elem.findall(".//" + qn("w:instrText")):
        if token in (instr.text or ""):
            return True
    return False


def _replace_token_in_paragraph(para: Any, token: str, value: str) -> bool:
    """Replace a token in a paragraph, handling both plain text and macrobutton XML fields cleanly."""
    if token in para.text:
        return _replace_in_paragraph(para, token, value)

    # Check macrobutton field replacement
    has_macrobutton = False
    p_elem = para._element
    for instr in p_elem.findall(".//" + qn("w:instrText")):
        if token in (instr.text or ""):
            has_macrobutton = True
            break
            
    if has_macrobutton:
        # Clear all child runs (w:r elements) in this paragraph
        for r in p_elem.findall(".//" + qn("w:r")):
            r.getparent().remove(r)
            
        # Add a new clean text run containing the replacement value
        para.add_run(value)
        return True
        
    return False


def _inject_text_placeholders(doc: Document, text_map: dict[str, str]) -> None:
    """Replace bracket-style and handlebars-style placeholders in paragraph text."""
    if not text_map:
        return

    def process_paragraph(para: Any) -> None:
        for token, val in text_map.items():
            _replace_token_in_paragraph(para, token, val)

    def process_container(container: Any) -> None:
        for para in container.paragraphs:
            process_paragraph(para)
        for table in container.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        process_paragraph(para)

    process_container(doc)
    for section in doc.sections:
        if section.header:
            process_container(section.header)
        if section.footer:
            process_container(section.footer)

    print(f"[TextReplace] Applied text placeholder replacement for {len(text_map)} tokens")


def _is_heading(para: Any) -> bool:
    """Helper to detect if a paragraph is a visual/semantic heading in the template."""
    style_name = (para.style.name or "").lower()
    if "heading" in style_name:
        return True
    # Heuristic: short, all-caps or contains bold text
    text = para.text.strip()
    if 2 < len(text) < 50:
        if text.isupper():
            return True
        if any(run.bold for run in para.runs if run.text.strip()):
            return True
    return False


def _match_section(current_section: str, field_section: str, field_name: str) -> float:
    """Calculate a semantic score between the active template section heading and manifest field metadata."""
    cs = re.sub(r"[^a-z]+", "", current_section.lower())
    fs = re.sub(r"[^a-z]+", "", field_section.lower())
    fn = re.sub(r"[^a-z]+", "", field_name.lower())
    
    if fs and (fs in cs or cs in fs):
        return 1.0
    if fn and (fn in cs or cs in fn):
        return 0.9
        
    keywords_map = {
        "skill": ["skill", "expertise", "competenc"],
        "qualification": ["qualification", "certific", "credential", "education"],
        "experience": ["experience", "employment", "history", "career", "work"],
    }
    
    for kw, synonyms in keywords_map.items():
        cs_match = any(syn in cs for syn in synonyms)
        fs_match = any(syn in fs for syn in synonyms) or any(syn in fn for syn in synonyms)
        if cs_match and fs_match:
            return 0.8
            
    return 0.0


def _inject_array_paragraphs(
    doc: Document,
    extracted: dict[str, Any],
    manifest_fields: list[dict[str, Any]]
) -> None:
    """Replicate bullet paragraph elements N times for arrays, mapping them dynamically based on sections."""
    array_fields: list[dict] = []
    for field in manifest_fields:
        fname = field.get("name", "")
        ftype = field.get("field_type", "scalar")
        inj = field.get("injection_details") or {}
        injection_type = inj.get("injection_type", "text_placeholder")
        
        if ftype in ("array", "array_object") and injection_type in ("text_placeholder", "handlebars"):
            val = extracted.get(fname)
            if not val:
                val = []
            elif not isinstance(val, list):
                val = [val]
                
            serialized_items = []
            for item in val:
                if isinstance(item, dict):
                    parts = [str(v) for v in item.values() if v is not None and str(v).strip()]
                    serialized_items.append("  ".join(parts) if parts else "")
                else:
                    serialized_items.append(str(item))
                    
            serialized_items = [s for s in serialized_items if s.strip()]
            token = inj.get("placeholder_text") or field.get("template_token") or f"{{{{{fname}}}}}"
            
            array_fields.append({
                "name": fname,
                "token": token,
                "section": field.get("layout_details", {}).get("section") or "",
                "items": serialized_items,
            })

    if not array_fields:
        return

    expanded_fields: set[str] = set()

    def process_container(container: Any) -> None:
        current_section = ""
        i = 0
        while i < len(container.paragraphs):
            para = container.paragraphs[i]
            
            if _is_heading(para):
                current_section = para.text.strip()
                
            matched_field = None
            matched_token = None
            best_score = -1.0
            
            for af in array_fields:
                token = af["token"]
                tokens_to_check = [token, f"{{{{{af['name']}}}}}", f"{{{{ {af['name']} }}}}"]
                
                found_token = None
                for t in tokens_to_check:
                    if t and _paragraph_contains_token(para, t):
                        found_token = t
                        break
                        
                if found_token:
                    score = _match_section(current_section, af["section"], af["name"])
                    if score > best_score:
                        best_score = score
                        matched_field = af
                        matched_token = found_token

            if matched_field and matched_token:
                fname = matched_field["name"]
                items = matched_field["items"]
                p_elem = para._element
                p_parent = p_elem.getparent()
                p_index = p_parent.index(p_elem)
                
                if fname not in expanded_fields:
                    expanded_fields.add(fname)
                    for item in items:
                        cloned_p = copy.deepcopy(p_elem)
                        cloned_para_obj = Paragraph(cloned_p, para._parent)
                        _replace_token_in_paragraph(cloned_para_obj, matched_token, item)
                        p_parent.insert(p_index, cloned_p)
                        p_index += 1
                    
                    p_parent.remove(p_elem)
                    i += len(items)
                else:
                    p_parent.remove(p_elem)
            else:
                i += 1

        for table in container.tables:
            for row in table.rows:
                for cell in row.cells:
                    process_container(cell)

    process_container(doc)


# ---------------------------------------------------------------------------
# Main injection dispatcher — uses injection_details from manifest
# ---------------------------------------------------------------------------

def inject_data_into_docx(
    docx_bytes: bytes,
    extracted: dict[str, Any],
    manifest_fields: list[dict[str, Any]],
) -> bytes:
    """Inject extracted resume values into the DOCX template using per-field injection strategy."""
    doc = Document(BytesIO(docx_bytes))

    mergefield_map: dict[str, str] = {}   # mergefield_name_in_xml → value
    text_placeholder_map: dict[str, str] = {}  # placeholder_text → value
    table_data_map: dict[str, list[dict[str, str]]] = {} # table_name -> list of dict values mapped by xml sub-field

    for field in manifest_fields:
        fname = field.get("name", "")
        ftype = field.get("field_type", "scalar")
        inj = field.get("injection_details") or {}
        injection_type = inj.get("injection_type", "text_placeholder")
        value = extracted.get(fname)
        serialized = _serialize_value(value, ftype)

        if injection_type == "mergefield":
            mf_name = inj.get("mergefield_name", "")
            if mf_name:
                mergefield_map[mf_name] = serialized
                print(f"  [Dispatch] {fname} → mergefield '{mf_name}' = {repr(serialized[:60])}")

        elif injection_type == "table_merge_row":
            table_name = inj.get("table_name", "")
            if table_name:
                raw_array = value or []
                if isinstance(raw_array, list):
                    items_mapped = []
                    for item in raw_array:
                        if isinstance(item, dict):
                            mapped_item = {}
                            sub_fields = field.get("sub_fields") or []
                            for skey, sval in item.items():
                                skey_norm = _normalize_field_name(skey)
                                sf_match = None
                                for sf in sub_fields:
                                    if sf.get("name") == skey_norm:
                                        sf_match = sf
                                        break
                                
                                xml_sf_name = None
                                if sf_match:
                                    sf_token = sf_match.get("template_token", "")
                                    if sf_token.upper().startswith("MERGEFIELD "):
                                        xml_sf_name = sf_token[len("MERGEFIELD "):].strip()
                                
                                if not xml_sf_name:
                                    xml_sf_name = skey
                                
                                mapped_item[xml_sf_name] = _serialize_value(sval, "scalar")
                            items_mapped.append(mapped_item)
                        elif item:
                            sub_fields = field.get("sub_fields") or []
                            xml_sf_name = "CheckType"
                            if sub_fields:
                                sf_token = sub_fields[0].get("template_token", "")
                                if sf_token.upper().startswith("MERGEFIELD "):
                                    xml_sf_name = sf_token[len("MERGEFIELD "):].strip()
                            items_mapped.append({xml_sf_name: _serialize_value(item, "scalar")})
                    
                    table_data_map[table_name] = items_mapped
                    print(f"  [Dispatch] {fname} → table_merge_row '{table_name}' ({len(items_mapped)} items) = {repr(serialized[:60])}")

        elif injection_type in ("text_placeholder", "handlebars"):
            placeholder = inj.get("placeholder_text", f"{{{{{fname}}}}}")
            if ftype in ("array", "array_object"):
                # Arrays/repeated bullet paragraphs are expanded by _inject_array_paragraphs directly
                pass
            else:
                if placeholder:
                    text_placeholder_map[placeholder] = serialized
                # Also add generic {{field_name}} variants as fallback
                text_placeholder_map[f"{{{{{fname}}}}}"] = serialized
                text_placeholder_map[f"{{{{ {fname} }}}}"] = serialized
                print(f"  [Dispatch] {fname} → text_placeholder '{placeholder}' = {repr(serialized[:60])}")

        else:
            if ftype not in ("array", "array_object"):
                token = field.get("template_token", f"{{{{{fname}}}}}")
                text_placeholder_map[token] = serialized
                text_placeholder_map[f"{{{{{fname}}}}}"] = serialized

    # Apply strategies
    print(f"[Injector] TableMergeRows to expand: {list(table_data_map.keys())}")
    print(f"[Injector] MergeFields to inject: {list(mergefield_map.keys())}")
    print(f"[Injector] Text placeholders to inject: {list(text_placeholder_map.keys())}")

    # Process table rows expansion first (since it duplicates mergefield markers)
    _inject_table_merge_rows(doc, table_data_map)
    _inject_array_paragraphs(doc, extracted, manifest_fields)
    _inject_mergefields(doc, mergefield_map)
    _inject_text_placeholders(doc, text_placeholder_map)

    out_io = BytesIO()
    doc.save(out_io)
    return out_io.getvalue()


def inject_render_payload_into_docx(template_bytes: bytes, payload: dict, manifest: dict) -> bytes:
    fields = manifest.get("fields", []) if isinstance(manifest, dict) else []
    data = {}
    data.update(payload.get("render_values", {}))
    data.update(payload.get("placeholder_values", {}))
    for block_name, items in (payload.get("repeat_blocks", {}) or {}).items():
        data[block_name] = items
    return inject_data_into_docx(template_bytes, data, fields)
