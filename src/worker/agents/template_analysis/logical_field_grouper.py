from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from copy import deepcopy
from typing import Any

MERGEFIELD_RE = re.compile(r"^MERGEFIELD\s+", re.I)
CAMEL_TOKEN_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|\d+")
logger = logging.getLogger(__name__)


def canonicalize_field_name(text: str) -> str:
    cleaned = MERGEFIELD_RE.sub("", (text or "").strip())
    cleaned = re.sub(r"^MACROBUTTON\s+AcceptAllChangesShown\s+", "", cleaned, flags=re.I)
    cleaned = cleaned.strip("[]{}()<>")
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", cleaned).strip("_").lower()
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned or "field"


def split_camel_case(name: str) -> list[str]:
    return CAMEL_TOKEN_RE.findall(name or "")


def _normalize_suffix_tokens(tokens: list[str]) -> list[str]:
    lowered = [t.lower() for t in tokens if t]
    compact = "".join(lowered)
    if compact in {"fullname", "name"}:
        return ["name"]
    if compact in {"id"}:
        return ["id"]
    if compact in {"tel", "telno", "phoneno", "phone", "mobile", "mobileno"}:
        return ["phone"]
    if compact in {"jobtitle", "title"}:
        return ["title"]
    return lowered


def normalize_mergefield_name(mergefield_or_token: str, label_text: str | None = None) -> str:
    raw = MERGEFIELD_RE.sub("", (mergefield_or_token or "").strip()).strip("{}")
    raw_name = re.split(r"\s+", raw, maxsplit=1)[0]
    parts = split_camel_case(raw_name)
    if not parts:
        return canonicalize_field_name(label_text or mergefield_or_token) or "field"
    prefix = parts[0].lower()
    suffix = _normalize_suffix_tokens(parts[1:])
    if prefix == "candidate" and suffix:
        return canonicalize_field_name("candidate_" + "_".join(suffix))
    if prefix == "employee" and suffix:
        return canonicalize_field_name("presenter_" + "_".join(suffix))
    return canonicalize_field_name("_".join(_normalize_suffix_tokens(parts))) or canonicalize_field_name(label_text or "") or "field"


def extract_public_token(token: str) -> str:
    tok = (token or "").strip()
    m = re.match(r'^MACROBUTTON\s+AcceptAllChangesShown\s+"(.+)"$', tok, flags=re.I)
    if m:
        return m.group(1)
    return tok


def infer_source_classification(field: dict) -> str:
    """Generic source classification from neutral lexical cues only."""
    text = " ".join(str(field.get(k, "")) for k in ("name", "display_label", "template_token")).lower()
    name = str(field.get("name") or "").lower()
    if any(k in text for k in ("recruiter", "consultant", "presenter", "employee", "interviewer")):
        return "recruiter_input"
    if name.endswith("_id") or "reference" in text or "req" in name:
        return "input_only"
    if any(k in text for k in ("salary", "notice", "availability", "start_date", "expected")):
        return "input_only"
    if any(k in text for k in ("comment", "opinion", "summary", "assessment")):
        return "generated"
    return "resume_fact"


def group_blocks_by_section(layout: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for block in layout.get("canonical_blocks", []):
        section = (block.get("section_heading") or "").strip().lower()
        grouped[section].append(block)
    return grouped


def _is_bullet_token(token: str) -> bool:
    t = token.lower()
    return "bullet" in t or "list" in t


def _group_identical_candidates(fields: list[dict]) -> list[dict]:
    buckets: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for field in fields:
        evidence = field.get("template_evidence") or {}
        buckets[(
            (evidence.get("section_heading") or "").strip().lower(),
            canonicalize_field_name(field.get("name") or field.get("suggested_name") or ""),
            str(field.get("template_token") or ""),
        )].append(field)

    merged: list[dict] = []
    for (_sec, _name, _tok), items in buckets.items():
        f = deepcopy(items[0])
        block_ids: list[str] = []
        for item in items:
            block_ids.extend(item.get("source_block_ids") or [])
        f["source_block_ids"] = sorted(set(block_ids))
        f.setdefault("render_contract", {})
        f["render_contract"].setdefault("occurrence_selector", {})
        f["render_contract"]["occurrence_selector"].update(
            {"section_heading": (f.get("template_evidence") or {}).get("section_heading"), "source_block_ids": f["source_block_ids"]}
        )

        label = f.get("display_label") or (f.get("template_evidence") or {}).get("label_text") or ""
        raw_name = f.get("name") or f.get("suggested_name") or label or f.get("template_token")
        raw_token = str(f.get("template_token") or "")
        f["raw_token"] = raw_token
        f["template_token"] = extract_public_token(raw_token)
        if raw_token.upper().startswith("MERGEFIELD"):
            normalized = normalize_mergefield_name(raw_token, label)
            aliases = set(f.get("aliases") or [])
            if f.get("name"):
                aliases.add(canonicalize_field_name(str(f.get("name"))))
            if f.get("suggested_name"):
                aliases.add(canonicalize_field_name(str(f.get("suggested_name"))))
            aliases.discard(normalized)
            if aliases:
                f["aliases"] = sorted(a for a in aliases if a)
            f["name"] = normalized
            f["suggested_name"] = normalized
            if not raw_token.upper().startswith("MERGEFIELD TABLESTART:") and not raw_token.upper().startswith("MERGEFIELD TABLEEND:"):
                f["field_type"] = "scalar"
        else:
            f["name"] = canonicalize_field_name(str(raw_name))
            if f.get("suggested_name"):
                f["name"] = canonicalize_field_name(str(f.get("suggested_name")))
        f["display_label"] = label
        f["source_classification"] = infer_source_classification(f)
        merged.append(f)
    return merged


def _build_repeat_section_field(section: str, fields: list[dict]) -> dict | None:
    token_fields: dict[str, list[dict]] = defaultdict(list)
    for field in fields:
        token = str(field.get("template_token") or "").strip()
        if token:
            token_fields[token].append(field)
    logger.info("[LogicalGrouper] section=%s token_candidates=%s", section.upper(), len(token_fields))
    if len(token_fields) < 2:
        return None

    freqs = {tok: len(items) for tok, items in token_fields.items()}
    repeated = [tok for tok, count in freqs.items() if count > 1]
    if len(repeated) < 2:
        proxy = {tok: len((items[0].get("source_block_ids") or [])) for tok, items in token_fields.items() if items}
        if len(proxy) >= 2 and len(set(proxy.values())) == 1 and next(iter(proxy.values())) > 1:
            repeated = list(proxy.keys())
            repeat_count = next(iter(proxy.values()))
        else:
            logger.info("[LogicalGrouper] section=%s repeat_tokens_found=0", section.upper())
            return None
    else:
        repeat_count = min(freqs[t] for t in repeated)
    logger.info("[LogicalGrouper] section=%s repeat_tokens_found=%s", section.upper(), len(repeated))
    sub_fields = []
    block_tokens = {}
    repeat_items: list[dict[str, str]] = []
    source_block_ids: list[str] = []

    for token in repeated:
        name = canonicalize_field_name(token)
        clean = extract_public_token(token)
        sub_fields.append({"name": name, "field_type": "array" if _is_bullet_token(token) else "scalar", "template_token": clean, "raw_token": token})
        block_tokens[name] = clean

    for idx in range(repeat_count):
        row: dict[str, str] = {}
        for sub in sub_fields:
            matched = token_fields[sub["template_token"]]
            source_ids = []
            if idx < len(matched):
                source_ids = matched[idx].get("source_block_ids") or []
            elif matched:
                all_ids = matched[0].get("source_block_ids") or []
                if idx < len(all_ids):
                    source_ids = [all_ids[idx]]
            if source_ids:
                row[sub["name"]] = source_ids[0]
                source_block_ids.extend(source_ids)
        repeat_items.append(row)
    logger.info("[LogicalGrouper] section=%s repeat_items=%s", section.upper(), len(repeat_items))

    heading = section.upper()
    grouped = {
        "name": canonicalize_field_name(section),
        "display_label": heading,
        "field_type": "array_object",
        "template_token": extract_public_token(repeated[0]),
        "raw_token": repeated[0],
        "source_block_ids": sorted(set(source_block_ids)),
        "sub_fields": sub_fields,
        "template_evidence": {"section_heading": heading, "placeholder_tokens": repeated},
        "render_contract": {
            "render_strategy": "repeat_block",
            "anchor_token": extract_public_token(repeated[0]),
            "block_tokens": block_tokens,
            "repeat_items": repeat_items,
            "occurrence_selector": {"section_heading": heading},
        },
        "source_classification": "resume_fact",
    }
    logger.info("[LogicalGrouper] section=%s grouped_field_created=%s", section.upper(), grouped["name"])
    return grouped


def group_logical_fields_from_candidates(fields: list[dict], layout: dict) -> list[dict]:
    merged = _group_identical_candidates(fields)
    table_regions: dict[str, list[dict]] = defaultdict(list)
    remaining: list[dict] = []
    for field in merged:
        raw = str(field.get("raw_token") or field.get("template_token") or "")
        if raw.upper().startswith("MERGEFIELD TABLESTART:"):
            region = raw.split(":", 1)[1].strip()
            table_regions[region].append(field)
            continue
        if raw.upper().startswith("MERGEFIELD TABLEEND:"):
            region = raw.split(":", 1)[1].strip()
            table_regions[region].append(field)
            continue
        remaining.append(field)
    merged = remaining

    by_section: dict[str, list[dict]] = defaultdict(list)
    for field in merged:
        sec = ((field.get("template_evidence") or {}).get("section_heading") or "").strip().lower()
        by_section[sec].append(field)

    logical: list[dict] = []
    for section, sec_fields in by_section.items():
        repeat = _build_repeat_section_field(section, sec_fields)
        if repeat:
            logical.append(repeat)
            continue

        if len(sec_fields) > 1:
            sec_name = canonicalize_field_name(section)
            if sec_name in {"education", "certifications", "training", "projects", "publications"}:
                sub_fields = []
                for f in sec_fields:
                    tok = str(f.get("template_token") or "")
                    sub_fields.append({"name": canonicalize_field_name(tok or f.get("name") or "field"), "field_type": "array" if _is_bullet_token(tok) else "scalar", "template_token": tok})
                logical.append({"name": sec_name, "display_label": section.upper(), "field_type": "array_object", "template_token": sub_fields[0]["template_token"] if sub_fields else "", "source_block_ids": sorted({bid for f in sec_fields for bid in (f.get("source_block_ids") or [])}), "sub_fields": sub_fields, "template_evidence": {"section_heading": section.upper()}, "render_contract": {"render_strategy": "repeat_block", "anchor_token": sub_fields[0]["template_token"] if sub_fields else "", "block_tokens": {sf["name"]: sf["template_token"] for sf in sub_fields}}, "source_classification": "resume_fact"})
                continue
            token_counts = Counter(str(f.get("template_token") or "") for f in sec_fields)
            if len(token_counts) == 1:
                f0 = deepcopy(sec_fields[0])
                f0["field_type"] = "array" if _is_bullet_token(f0.get("template_token") or "") else f0.get("field_type", "scalar")
                f0.setdefault("render_contract", {})["render_strategy"] = "bullet_list_replace" if f0["field_type"] == "array" else "placeholder_replace"
                f0["name"] = canonicalize_field_name(section or f0.get("name") or "field")
                f0["source_block_ids"] = sorted({bid for f in sec_fields for bid in (f.get("source_block_ids") or [])})
                logical.append(f0)
                continue

        logical.extend(sec_fields)

    for field in logical:
        preferred_name = field.get("suggested_name") or field.get("name") or field.get("display_label") or "field"
        field["name"] = canonicalize_field_name(preferred_name)
        field["source_classification"] = infer_source_classification(field)

    dedup: dict[str, dict] = {}
    for field in logical:
        name = field.get("name") or "field"
        if name not in dedup:
            dedup[name] = field
            continue
        existing = dedup[name]
        existing["source_block_ids"] = sorted(set((existing.get("source_block_ids") or []) + (field.get("source_block_ids") or [])))
        if existing.get("field_type") != "array_object" and field.get("field_type") == "array_object":
            dedup[name] = field
    for region in table_regions:
        region_lower = canonicalize_field_name(region)
        members = [f for f in merged if str(f.get("raw_token") or "").upper().startswith("MERGEFIELD") and not str(f.get("raw_token") or "").upper().startswith("MERGEFIELD TABLE")]
        if not members:
            continue
        sub_fields = []
        block_tokens = {}
        source_ids: list[str] = []
        for m in members:
            sub_name = normalize_mergefield_name(str(m.get("raw_token") or ""))
            token = str(m.get("template_token") or "")
            sub_fields.append({"name": sub_name, "field_type": "scalar", "template_token": token, "raw_token": str(m.get("raw_token") or "")})
            block_tokens[sub_name] = token
            source_ids.extend(m.get("source_block_ids") or [])
        dedup[region_lower] = {
            "name": region_lower,
            "display_label": region,
            "field_type": "array_object",
            "template_token": sub_fields[0]["template_token"],
            "raw_token": sub_fields[0]["raw_token"],
            "source_block_ids": sorted(set(source_ids)),
            "sub_fields": sub_fields,
            "template_evidence": {"section_heading": region},
            "render_contract": {"render_strategy": "mailmerge_table_region", "region_name": region, "block_tokens": block_tokens, "anchor_token": sub_fields[0]["template_token"]},
            "source_classification": "resume_fact",
        }
    return list(dedup.values())
