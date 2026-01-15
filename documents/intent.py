from dataclasses import dataclass, field
from difflib import SequenceMatcher
import re
import unicodedata

from .intent_catalog import SYNONYM_MAP, TYPE_BY_BUILTIN

FUZZY_THRESHOLD = 0.84


@dataclass
class ResolvedIntent:
    kind: str
    builtin_key: str = ""
    inferred_type: str = ""
    anchors: list[str] = field(default_factory=list)
    match_strategy: str = ""
    confidence: float = 0.0


def _normalize_label(value: str) -> str:
    raw = (value or "").strip().lower()
    normalized = unicodedata.normalize("NFKD", raw)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped)


def _infer_type(normalized: str, builtin_key: str = "") -> str:
    if builtin_key:
        return TYPE_BY_BUILTIN.get(builtin_key, "text")
    if "cnpj" in normalized:
        return "cnpj"
    if "cpf" in normalized:
        return "cpf"
    if "barra" in normalized or "linha" in normalized or "barcode" in normalized:
        return "barcode"
    if "vencimento" in normalized or "data" in normalized:
        return "date"
    if any(term in normalized for term in ("valor", "total", "juros", "multa", "preco")):
        return "money"
    if "cep" in normalized:
        return "postal"
    if any(term in normalized for term in ("endereco", "logradouro", "rua", "avenida")):
        return "address"
    if any(term in normalized for term in ("numero", "n ", "no ", "matricula", "cliente")):
        return "id"
    return "text"


def _build_builtin_candidates(builtin_fields):
    candidates = []
    for key, label in builtin_fields:
        key_norm = _normalize_label(key)
        label_norm = _normalize_label(label)
        if key_norm:
            candidates.append((key_norm, key, "exact"))
        if label_norm:
            candidates.append((label_norm, key, "label"))
    for synonym, key in SYNONYM_MAP.items():
        candidates.append((_normalize_label(synonym), key, "synonym"))
    return candidates


def resolve_intent(label: str, builtin_fields, allow_llm=False) -> ResolvedIntent:
    normalized = _normalize_label(label)
    if not normalized:
        return ResolvedIntent(kind="custom", inferred_type="text", match_strategy="empty", confidence=0.0)

    candidates = _build_builtin_candidates(builtin_fields)
    exact_lookup = {candidate: (key, strategy) for candidate, key, strategy in candidates}

    if normalized in exact_lookup:
        key, strategy = exact_lookup[normalized]
        anchors = _build_anchors(label, key, builtin_fields)
        return ResolvedIntent(
            kind="builtin",
            builtin_key=key,
            inferred_type=_infer_type(normalized, key),
            anchors=anchors,
            match_strategy=strategy,
            confidence=1.0,
        )

    best_key = ""
    best_score = 0.0
    best_strategy = ""
    for candidate, key, strategy in candidates:
        score = SequenceMatcher(None, normalized, candidate).ratio()
        if score > best_score:
            best_score = score
            best_key = key
            best_strategy = strategy
    if best_key and best_score >= FUZZY_THRESHOLD:
        anchors = _build_anchors(label, best_key, builtin_fields)
        return ResolvedIntent(
            kind="builtin",
            builtin_key=best_key,
            inferred_type=_infer_type(normalized, best_key),
            anchors=anchors,
            match_strategy="fuzzy",
            confidence=best_score,
        )

    if allow_llm:
        llm_result = resolve_intent_with_llm(label)
        if llm_result:
            return llm_result

    return ResolvedIntent(
        kind="custom",
        inferred_type=_infer_type(normalized),
        anchors=[label.strip()] if label.strip() else [],
        match_strategy="custom",
        confidence=0.0,
    )


def _build_anchors(label: str, builtin_key: str, builtin_fields):
    anchors = []
    label_value = (label or "").strip()
    if label_value:
        anchors.append(label_value)

    builtin_label = ""
    for key, field_label in builtin_fields:
        if key == builtin_key:
            builtin_label = field_label
            break
    if builtin_label:
        anchors.append(builtin_label)

    for synonym, key in SYNONYM_MAP.items():
        if key == builtin_key:
            anchors.append(synonym)

    seen = set()
    unique = []
    for anchor in anchors:
        norm = _normalize_label(anchor)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        unique.append(anchor)
    return unique


def resolve_intent_with_llm(label: str) -> ResolvedIntent | None:
    return None
