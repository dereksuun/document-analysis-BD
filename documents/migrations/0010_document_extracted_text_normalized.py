import re
import unicodedata

from django.db import migrations, models


def _normalize_for_match(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped).strip().lower()


def backfill_normalized_text(apps, schema_editor):
    Document = apps.get_model("documents", "Document")
    qs = (
        Document.objects.filter(extracted_text_normalized="")
        .exclude(extracted_text="")
    )
    for doc in qs.iterator():
        doc.extracted_text_normalized = _normalize_for_match(doc.extracted_text)
        doc.save(update_fields=["extracted_text_normalized"])


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0009_document_text_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="extracted_text_normalized",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.RunPython(backfill_normalized_text, migrations.RunPython.noop),
    ]
