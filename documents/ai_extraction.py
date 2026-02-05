import json
import logging
from typing import Any

from django.conf import settings
from django.utils import timezone

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency in local env
    OpenAI = None


logger = logging.getLogger(__name__)

DOC_TYPE_CHOICES = {
    "curriculo",
    "contrato",
    "nota_fiscal",
    "boleto",
    "fatura",
    "recibo",
    "comprovante",
    "outro",
}
SENIORITY_CHOICES = {"junior", "pleno", "senior", "lead", "unknown"}
SKILL_LEVEL_CHOICES = {"unknown", "basic", "intermediate", "advanced"}
REASONING_EFFORT_CHOICES = {"minimal", "low", "medium", "high"}

AI_EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "doc_type": {"type": "string", "enum": sorted(DOC_TYPE_CHOICES)},
        "person": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "name": {"type": ["string", "null"]},
                "emails": {"type": "array", "items": {"type": "string"}},
                "phones": {"type": "array", "items": {"type": "string"}},
                "location": {"type": ["string", "null"]},
                "age_estimate_years": {
                    "type": ["integer", "null"],
                    "minimum": 0,
                    "maximum": 120,
                },
                "age_evidence": {"type": ["string", "null"]},
            },
            "required": [
                "name",
                "emails",
                "phones",
                "location",
                "age_estimate_years",
                "age_evidence",
            ],
        },
        "experience": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "years_estimate": {
                    "type": ["integer", "null"],
                    "minimum": 0,
                    "maximum": 60,
                },
                "years_evidence": {"type": ["string", "null"]},
                "seniority": {"type": "string", "enum": sorted(SENIORITY_CHOICES)},
                "roles": {"type": "array", "items": {"type": "string"}},
                "companies": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "years_estimate",
                "years_evidence",
                "seniority",
                "roles",
                "companies",
            ],
        },
        "skills": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "level": {"type": "string", "enum": sorted(SKILL_LEVEL_CHOICES)},
                    "evidence": {"type": "string"},
                },
                "required": ["name", "level", "evidence"],
            },
        },
        "education": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "degree": {"type": ["string", "null"]},
                    "institution": {"type": ["string", "null"]},
                    "evidence": {"type": "string"},
                },
                "required": ["degree", "institution", "evidence"],
            },
        },
        "keywords_evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "term": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": ["term", "evidence"],
            },
        },
        "confidence": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "overall": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                }
            },
            "required": ["overall"],
        },
    },
    "required": [
        "doc_type",
        "person",
        "experience",
        "skills",
        "education",
        "keywords_evidence",
        "confidence",
    ],
}

SYSTEM_PROMPT = (
    "Voce eh um extrator de informacoes para documentos em portugues e ingles. "
    "Retorne somente JSON valido seguindo o schema. "
    "Nao invente dados. Se nao houver evidencias, use null, lista vazia, "
    "'unknown' ou 'outro' conforme o campo. "
    "Sempre que inferir algo, preencha o campo de evidence com um trecho curto do texto."
)


def _clean_text(value: Any, *, max_len: int = 300) -> str:
    if value is None:
        return ""
    cleaned = " ".join(str(value).split()).strip()
    if max_len and len(cleaned) > max_len:
        return cleaned[:max_len].rstrip()
    return cleaned


def _clean_optional_text(value: Any, *, max_len: int = 300) -> str | None:
    cleaned = _clean_text(value, max_len=max_len)
    return cleaned or None


def _clean_int(value: Any, *, min_value: int, max_value: int) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed < min_value or parsed > max_value:
        return None
    return parsed


def _clean_float(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    if parsed < 0:
        return 0.0
    if parsed > 1:
        return 1.0
    return parsed


def _clean_list(values: Any, *, max_items: int = 20, max_len: int = 120) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = _clean_text(raw, max_len=max_len)
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(text)
        if len(cleaned) >= max_items:
            break
    return cleaned


def _normalize_skill(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    name = _clean_text(raw.get("name"), max_len=120)
    if not name:
        return None
    level = _clean_text(raw.get("level"), max_len=20).lower() or "unknown"
    if level not in SKILL_LEVEL_CHOICES:
        level = "unknown"
    evidence = _clean_text(raw.get("evidence"), max_len=220)
    if not evidence:
        return None
    return {"name": name, "level": level, "evidence": evidence}


def _normalize_education(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    degree = _clean_optional_text(raw.get("degree"), max_len=160)
    institution = _clean_optional_text(raw.get("institution"), max_len=160)
    evidence = _clean_text(raw.get("evidence"), max_len=220)
    if not evidence:
        return None
    return {
        "degree": degree,
        "institution": institution,
        "evidence": evidence,
    }


def _normalize_keyword_evidence(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    term = _clean_text(raw.get("term"), max_len=120)
    evidence = _clean_text(raw.get("evidence"), max_len=220)
    if not term or not evidence:
        return None
    return {"term": term, "evidence": evidence}


def normalize_ai_payload(payload: dict) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    person_raw = payload.get("person") if isinstance(payload.get("person"), dict) else {}
    exp_raw = payload.get("experience") if isinstance(payload.get("experience"), dict) else {}
    confidence_raw = payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}

    doc_type = _clean_text(payload.get("doc_type"), max_len=40).lower() or "outro"
    if doc_type not in DOC_TYPE_CHOICES:
        doc_type = "outro"

    seniority = _clean_text(exp_raw.get("seniority"), max_len=20).lower() or "unknown"
    if seniority not in SENIORITY_CHOICES:
        seniority = "unknown"

    skills: list[dict] = []
    for item in payload.get("skills") if isinstance(payload.get("skills"), list) else []:
        normalized = _normalize_skill(item)
        if normalized:
            skills.append(normalized)
        if len(skills) >= 30:
            break

    education: list[dict] = []
    for item in payload.get("education") if isinstance(payload.get("education"), list) else []:
        normalized = _normalize_education(item)
        if normalized:
            education.append(normalized)
        if len(education) >= 20:
            break

    keywords_evidence: list[dict] = []
    for item in payload.get("keywords_evidence") if isinstance(payload.get("keywords_evidence"), list) else []:
        normalized = _normalize_keyword_evidence(item)
        if normalized:
            keywords_evidence.append(normalized)
        if len(keywords_evidence) >= 40:
            break

    return {
        "doc_type": doc_type,
        "person": {
            "name": _clean_optional_text(person_raw.get("name"), max_len=160),
            "emails": _clean_list(person_raw.get("emails"), max_items=10, max_len=120),
            "phones": _clean_list(person_raw.get("phones"), max_items=10, max_len=32),
            "location": _clean_optional_text(person_raw.get("location"), max_len=160),
            "age_estimate_years": _clean_int(
                person_raw.get("age_estimate_years"),
                min_value=0,
                max_value=120,
            ),
            "age_evidence": _clean_optional_text(person_raw.get("age_evidence"), max_len=220),
        },
        "experience": {
            "years_estimate": _clean_int(
                exp_raw.get("years_estimate"),
                min_value=0,
                max_value=60,
            ),
            "years_evidence": _clean_optional_text(exp_raw.get("years_evidence"), max_len=220),
            "seniority": seniority,
            "roles": _clean_list(exp_raw.get("roles"), max_items=20, max_len=120),
            "companies": _clean_list(exp_raw.get("companies"), max_items=20, max_len=120),
        },
        "skills": skills,
        "education": education,
        "keywords_evidence": keywords_evidence,
        "confidence": {"overall": _clean_float(confidence_raw.get("overall"))},
    }


def is_ai_extraction_enabled() -> bool:
    if OpenAI is None:
        return False
    api_key = (getattr(settings, "OPENAI_API_KEY", "") or "").strip()
    if not api_key:
        return False
    enabled = str(getattr(settings, "AI_EXTRACTION_ENABLED", "")).strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        return False
    return True


def _truncate_text(text: str, *, max_chars: int) -> tuple[str, bool]:
    normalized = (text or "").strip()
    if max_chars <= 0:
        return normalized, False
    if len(normalized) <= max_chars:
        return normalized, False
    return normalized[:max_chars], True


def _extract_json_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    payload = None
    if hasattr(response, "model_dump"):
        payload = response.model_dump(mode="python")
    elif hasattr(response, "to_dict"):
        payload = response.to_dict()
    elif isinstance(response, dict):
        payload = response

    if not isinstance(payload, dict):
        raise ValueError("OpenAI response without JSON payload.")

    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            if content.get("type") not in {"output_text", "text"}:
                continue
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                return text
    raise ValueError("OpenAI response without output text.")


def _coerce_reasoning_effort(value: Any) -> str:
    effort = _clean_text(value, max_len=12).lower() or "low"
    if effort not in REASONING_EFFORT_CHOICES:
        return "low"
    return effort


def extract_structured(text: str, *, filename: str = "") -> tuple[dict, dict]:
    if not is_ai_extraction_enabled():
        raise RuntimeError("AI extraction is disabled.")
    if not text or not text.strip():
        raise ValueError("Document text is empty.")

    api_key = (getattr(settings, "OPENAI_API_KEY", "") or "").strip()
    model = (getattr(settings, "OPENAI_MODEL", "") or "gpt-5-mini").strip()
    schema_version = (
        getattr(settings, "AI_EXTRACTION_SCHEMA_VERSION", "")
        or "2026-02-02.v1"
    ).strip()
    max_chars = int(getattr(settings, "AI_EXTRACTION_MAX_TEXT_CHARS", 24000) or 24000)
    max_output_tokens = int(
        getattr(settings, "AI_EXTRACTION_MAX_OUTPUT_TOKENS", 1200) or 1200
    )
    timeout_seconds = int(getattr(settings, "AI_EXTRACTION_TIMEOUT_SECONDS", 60) or 60)
    reasoning_effort = _coerce_reasoning_effort(
        getattr(settings, "OPENAI_REASONING_EFFORT", "low")
    )

    trimmed_text, truncated = _truncate_text(text, max_chars=max_chars)
    user_prompt = (
        f"Arquivo: {filename or 'desconhecido'}\n"
        "Texto bruto do documento:\n"
        f"{trimmed_text}"
    )

    client = OpenAI(api_key=api_key, timeout=timeout_seconds)
    request_payload = {
        "model": model,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "document_ai_extraction",
                "strict": True,
                "schema": AI_EXTRACTION_SCHEMA,
            }
        },
        "max_output_tokens": max_output_tokens,
        "reasoning": {"effort": reasoning_effort},
    }

    response = client.responses.create(**request_payload)
    raw_output = _extract_json_text(response)
    parsed = json.loads(raw_output)
    normalized = normalize_ai_payload(parsed)

    meta = {
        "provider": "openai",
        "model": _clean_text(getattr(response, "model", None), max_len=80) or model,
        "schema_version": schema_version,
        "created_at": timezone.now().isoformat(),
        "reasoning_effort": reasoning_effort,
        "input_chars": len(trimmed_text),
        "input_truncated": truncated,
        "response_id": _clean_optional_text(getattr(response, "id", None), max_len=120),
    }
    logger.info(
        "ai_extract_response model=%s response_id=%s truncated=%s confidence=%s",
        meta["model"],
        meta["response_id"] or "-",
        truncated,
        normalized["confidence"]["overall"],
    )
    return normalized, meta
