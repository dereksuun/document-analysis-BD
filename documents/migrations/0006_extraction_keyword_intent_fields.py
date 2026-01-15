import re
import unicodedata

from django.db import migrations, models


SYNONYM_MAP = {
    "codigo de barras": "barcode",
    "linha digitavel": "barcode",
    "barcode": "barcode",
    "vencimento": "due_date",
    "data de vencimento": "due_date",
    "data vencimento": "due_date",
    "valor": "document_value",
    "valor do documento": "document_value",
    "valor total": "document_value",
    "total a pagar": "document_value",
    "cnpj": "cnpj",
    "cpf": "cpf",
    "juros": "juros",
    "multa": "multa",
    "endereco de cobranca": "billing_address",
    "local de cobranca": "billing_address",
    "nome do cedente": "payee_name",
    "nome do sacado": "payer_name",
    "nosso numero": "document_number",
    "numero do documento": "document_number",
    "numero da conta": "document_number",
    "instrucoes": "instructions",
}

TYPE_BY_BUILTIN = {
    "due_date": "date",
    "document_value": "money",
    "barcode": "barcode",
    "billing_address": "address",
    "cnpj": "cnpj",
    "cpf": "cpf",
    "payee_name": "text",
    "payer_name": "text",
    "document_number": "id",
    "instructions": "text",
    "juros": "money",
    "multa": "money",
}


def _normalize(value: str) -> str:
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


def backfill_keyword_intents(apps, schema_editor):
    ExtractionKeyword = apps.get_model("documents", "ExtractionKeyword")
    ExtractionField = apps.get_model("documents", "ExtractionField")

    builtin_fields = list(ExtractionField.objects.values_list("key", "label"))
    builtin_by_norm = {}
    for key, label in builtin_fields:
        builtin_by_norm[_normalize(key)] = key
        builtin_by_norm[_normalize(label)] = key
    for synonym, key in SYNONYM_MAP.items():
        builtin_by_norm[_normalize(synonym)] = key

    for keyword in ExtractionKeyword.objects.all():
        normalized = _normalize(keyword.label)
        builtin_key = keyword.field_key
        match_strategy = "stored" if builtin_key else ""
        confidence = 1.0 if builtin_key else 0.0

        if not builtin_key and normalized in builtin_by_norm:
            builtin_key = builtin_by_norm[normalized]
            match_strategy = "synonym"
            confidence = 1.0

        resolved_kind = "builtin" if builtin_key else "custom"
        inferred_type = _infer_type(normalized, builtin_key)

        anchors = [keyword.label]
        if builtin_key:
            for key, label in builtin_fields:
                if key == builtin_key:
                    anchors.append(label)
                    break
        keyword.field_key = builtin_key or ""
        keyword.resolved_kind = resolved_kind
        keyword.inferred_type = inferred_type
        keyword.anchors = anchors
        keyword.match_strategy = match_strategy
        keyword.confidence = confidence
        keyword.save(
            update_fields=[
                "field_key",
                "resolved_kind",
                "inferred_type",
                "anchors",
                "match_strategy",
                "confidence",
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0005_extraction_keyword_field_key"),
    ]

    operations = [
        migrations.AddField(
            model_name="extractionkeyword",
            name="resolved_kind",
            field=models.CharField(default="custom", max_length=16),
        ),
        migrations.AddField(
            model_name="extractionkeyword",
            name="inferred_type",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="extractionkeyword",
            name="anchors",
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name="extractionkeyword",
            name="match_strategy",
            field=models.CharField(blank=True, default="", max_length=24),
        ),
        migrations.AddField(
            model_name="extractionkeyword",
            name="confidence",
            field=models.FloatField(default=0.0),
        ),
        migrations.RunPython(backfill_keyword_intents, reverse_code=migrations.RunPython.noop),
    ]
