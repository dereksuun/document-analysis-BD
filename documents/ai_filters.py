from typing import Any

from .services import _normalize_for_match


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _clean_text(value: Any, *, max_len: int = 320) -> str:
    if value is None:
        return ""
    cleaned = " ".join(str(value).split()).strip()
    if max_len and len(cleaned) > max_len:
        return cleaned[:max_len].rstrip()
    return cleaned


def _truncate(text: str, *, max_len: int = 120) -> str:
    clean = _clean_text(text, max_len=max(max_len * 4, max_len))
    if len(clean) <= max_len:
        return clean
    return f"{clean[: max_len - 3].rstrip()}..."


def _safe_int(value: Any, *, min_value: int, max_value: int) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed < min_value or parsed > max_value:
        return None
    return parsed


def get_ai_payload(doc_or_json: Any) -> dict:
    if isinstance(doc_or_json, dict):
        source = doc_or_json
    else:
        source = getattr(doc_or_json, "extracted_json", {})
    source = _as_dict(source)
    return _as_dict(source.get("ai"))


def _iter_search_chunks(ai_payload: dict):
    if not ai_payload:
        return
    doc_type = _clean_text(ai_payload.get("doc_type"), max_len=80)
    if doc_type:
        yield doc_type

    person = _as_dict(ai_payload.get("person"))
    for key in ("name", "location", "age_evidence"):
        value = _clean_text(person.get(key), max_len=220)
        if value:
            yield value
    for field in ("emails", "phones"):
        for value in _as_list(person.get(field)):
            text = _clean_text(value, max_len=120)
            if text:
                yield text

    experience = _as_dict(ai_payload.get("experience"))
    for key in ("seniority", "years_evidence"):
        value = _clean_text(experience.get(key), max_len=220)
        if value:
            yield value
    years_estimate = experience.get("years_estimate")
    if years_estimate is not None:
        yield str(years_estimate)
    for field in ("roles", "companies"):
        for value in _as_list(experience.get(field)):
            text = _clean_text(value, max_len=120)
            if text:
                yield text

    for skill in _as_list(ai_payload.get("skills")):
        skill_data = _as_dict(skill)
        for key in ("name", "level", "evidence"):
            value = _clean_text(skill_data.get(key), max_len=220)
            if value:
                yield value

    for entry in _as_list(ai_payload.get("education")):
        item = _as_dict(entry)
        for key in ("degree", "institution", "evidence"):
            value = _clean_text(item.get(key), max_len=220)
            if value:
                yield value

    for entry in _as_list(ai_payload.get("keywords_evidence")):
        item = _as_dict(entry)
        for key in ("term", "evidence"):
            value = _clean_text(item.get(key), max_len=220)
            if value:
                yield value


def build_ai_search_blob(ai_payload: dict) -> str:
    chunks: list[str] = []
    seen: set[str] = set()
    for chunk in _iter_search_chunks(_as_dict(ai_payload)):
        normalized = _normalize_for_match(chunk)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        chunks.append(normalized)
    return " ".join(chunks)


def _build_document_blob(doc) -> str:
    ai_blob = build_ai_search_blob(get_ai_payload(doc))
    text_blob = _clean_text(getattr(doc, "text_content_norm", ""), max_len=0)
    if not text_blob:
        raw_text = (
            getattr(doc, "text_content", "")
            or getattr(doc, "extracted_text", "")
            or ""
        )
        text_blob = _normalize_for_match(raw_text)
    if ai_blob and text_blob:
        return f"{ai_blob} {text_blob}"
    return ai_blob or text_blob


def document_matches_terms(doc, terms: list[str], *, mode: str = "all") -> bool:
    if not terms:
        return True
    blob = _build_document_blob(doc)
    if not blob:
        return False
    if mode == "any":
        return any(term in blob for term in terms)
    return all(term in blob for term in terms)


def document_matches_excludes(doc, exclude_terms: list[str]) -> bool:
    if not exclude_terms:
        return False
    blob = _build_document_blob(doc)
    if not blob:
        return False
    return any(term in blob for term in exclude_terms)


def resolve_experience_years(doc) -> int | None:
    ai_payload = get_ai_payload(doc)
    experience = _as_dict(ai_payload.get("experience"))
    ai_value = _safe_int(experience.get("years_estimate"), min_value=0, max_value=60)
    if ai_value is not None:
        return ai_value
    return _safe_int(getattr(doc, "extracted_experience_years", None), min_value=0, max_value=60)


def resolve_age_years(doc) -> int | None:
    ai_payload = get_ai_payload(doc)
    person = _as_dict(ai_payload.get("person"))
    ai_value = _safe_int(person.get("age_estimate_years"), min_value=0, max_value=120)
    if ai_value is not None:
        return ai_value
    return _safe_int(getattr(doc, "extracted_age_years", None), min_value=0, max_value=120)


def document_passes_ranges(
    doc,
    *,
    experience_min_years: int | None = None,
    experience_max_years: int | None = None,
    age_min_years: int | None = None,
    age_max_years: int | None = None,
    exclude_unknowns: bool = False,
) -> bool:
    experience_value = resolve_experience_years(doc)
    age_value = resolve_age_years(doc)

    if experience_min_years is not None:
        if experience_value is None:
            if exclude_unknowns:
                return False
        elif experience_value < experience_min_years:
            return False
    if experience_max_years is not None:
        if experience_value is None:
            if exclude_unknowns:
                return False
        elif experience_value > experience_max_years:
            return False

    if age_min_years is not None:
        if age_value is None:
            if exclude_unknowns:
                return False
        elif age_value < age_min_years:
            return False
    if age_max_years is not None:
        if age_value is None:
            if exclude_unknowns:
                return False
        elif age_value > age_max_years:
            return False
    return True


def document_passes_semantic_filters(
    doc,
    *,
    terms: list[str],
    mode: str,
    exclude_terms: list[str],
    experience_min_years: int | None,
    experience_max_years: int | None,
    age_min_years: int | None,
    age_max_years: int | None,
    exclude_unknowns: bool,
) -> bool:
    if not document_matches_terms(doc, terms, mode=mode):
        return False
    if document_matches_excludes(doc, exclude_terms):
        return False
    if not document_passes_ranges(
        doc,
        experience_min_years=experience_min_years,
        experience_max_years=experience_max_years,
        age_min_years=age_min_years,
        age_max_years=age_max_years,
        exclude_unknowns=exclude_unknowns,
    ):
        return False
    return True


def _build_evidence_index(ai_payload: dict) -> list[tuple[str, str]]:
    evidence_index: list[tuple[str, str]] = []

    def _append(label: str, evidence: Any):
        evidence_text = _clean_text(evidence, max_len=300)
        if not evidence_text:
            return
        label_text = _clean_text(label, max_len=180)
        searchable = _normalize_for_match(f"{label_text} {evidence_text}")
        if not searchable:
            return
        evidence_index.append((searchable, evidence_text))

    experience = _as_dict(ai_payload.get("experience"))
    _append(
        f"experience {experience.get('seniority')}",
        experience.get("years_evidence"),
    )

    person = _as_dict(ai_payload.get("person"))
    _append("age person", person.get("age_evidence"))

    for item in _as_list(ai_payload.get("keywords_evidence")):
        entry = _as_dict(item)
        _append(entry.get("term") or "keyword", entry.get("evidence"))

    for item in _as_list(ai_payload.get("skills")):
        entry = _as_dict(item)
        _append(entry.get("name") or "skill", entry.get("evidence"))

    for item in _as_list(ai_payload.get("education")):
        entry = _as_dict(item)
        label = f"{entry.get('degree') or ''} {entry.get('institution') or ''}".strip() or "education"
        _append(label, entry.get("evidence"))

    return evidence_index


def find_evidence_snippet(
    doc,
    terms: list[str],
    *,
    max_len: int = 120,
    use_first_if_no_term: bool = False,
) -> str:
    ai_payload = get_ai_payload(doc)
    if not ai_payload:
        return ""
    evidence_index = _build_evidence_index(ai_payload)
    if not evidence_index:
        return ""
    for term in terms or []:
        for searchable, evidence in evidence_index:
            if term in searchable:
                return _truncate(evidence, max_len=max_len)
    if use_first_if_no_term:
        return _truncate(evidence_index[0][1], max_len=max_len)
    return ""
