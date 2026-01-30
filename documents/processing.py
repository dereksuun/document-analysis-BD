import re
from decimal import Decimal, InvalidOperation

from django.utils.dateparse import parse_date

from .models import Document, ExtractionKeyword
from .services import (
    KEYWORD_PREFIX,
    _normalize_for_match,
    extract_age_years,
    extract_contact_phone,
    extract_experience_years,
)


def get_keyword_map(owner_id, selected_fields):
    keyword_ids = []
    for field in selected_fields or []:
        if not field.startswith(KEYWORD_PREFIX):
            continue
        raw_id = field.split(":", 1)[1]
        if not raw_id.isdigit():
            continue
        keyword_ids.append(int(raw_id))
    if not keyword_ids:
        return {}
    keywords = ExtractionKeyword.objects.filter(owner_id=owner_id, id__in=keyword_ids)
    mapping = {}
    for keyword in keywords:
        mapping[f"{KEYWORD_PREFIX}{keyword.id}"] = {
            "label": keyword.label,
            "resolved_kind": keyword.resolved_kind,
            "field_key": keyword.field_key,
            "inferred_type": keyword.inferred_type,
            "value_type": keyword.value_type,
            "strategy": keyword.strategy,
            "strategy_params": keyword.strategy_params or {},
            "anchors": keyword.anchors or [],
            "match_strategy": keyword.match_strategy,
            "confidence": keyword.confidence,
        }
    return mapping


_NON_DIGIT_RE = re.compile(r"\D+")


def _normalize_digits(value: object, *, max_len: int | None = None, exact_len: int | None = None) -> str:
    if value is None:
        return ""
    digits = _NON_DIGIT_RE.sub("", str(value))
    if not digits:
        return ""
    if exact_len is not None and len(digits) != exact_len:
        return ""
    if max_len is not None and len(digits) > max_len:
        return digits[:max_len]
    return digits


def _clean_text(value: object, *, max_len: int | None = None) -> str:
    if value is None:
        return ""
    text = " ".join(str(value).split()).strip()
    if max_len is not None and len(text) > max_len:
        return text[:max_len]
    return text


def _parse_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value)).quantize(Decimal("0.01"))
        except InvalidOperation:
            return None
    raw = str(value).strip()
    if not raw:
        return None
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw and "." not in raw:
        raw = raw.replace(",", ".")
    try:
        return Decimal(raw).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _parse_date_value(value: object):
    if not value:
        return None
    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        return value
    return parse_date(str(value))


def apply_extracted_fields(doc: Document, extracted_text: str, payload: dict):
    text_value = extracted_text or ""
    normalized = _normalize_for_match(text_value)
    doc.extracted_text_normalized = normalized
    doc.text_content = text_value
    doc.text_content_norm = normalized
    doc.document_type = (payload or {}).get("document_type") or ""
    fields = (payload or {}).get("fields") or {}
    if not isinstance(fields, dict):
        fields = {}
    doc.issue_date = _parse_date_value(fields.get("issue_date"))
    doc.due_date = _parse_date_value(fields.get("due_date"))
    doc.document_value = _parse_decimal(fields.get("document_value"))
    doc.juros = _parse_decimal(fields.get("juros"))
    doc.multa = _parse_decimal(fields.get("multa"))
    doc.barcode = _normalize_digits(fields.get("barcode"), max_len=48)
    doc.payee_name = _clean_text(fields.get("payee_name"), max_len=200)
    doc.payer_name = _clean_text(fields.get("payer_name"), max_len=200)
    doc.payee_cnpj = _normalize_digits(fields.get("payee_cnpj") or fields.get("cnpj"), exact_len=14)
    doc.payer_cnpj = _normalize_digits(fields.get("payer_cnpj"), exact_len=14)
    doc.cpf = _normalize_digits(fields.get("cpf"), exact_len=11)
    doc.document_number = _clean_text(fields.get("document_number"), max_len=64)
    doc.contact_phone = extract_contact_phone(text_value)
    doc.extracted_age_years = extract_age_years(text_value)
    doc.extracted_experience_years = extract_experience_years(text_value)
