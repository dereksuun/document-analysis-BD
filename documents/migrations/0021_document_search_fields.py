from django.db import migrations, models


def add_issue_date_field(apps, schema_editor):
    ExtractionField = apps.get_model("documents", "ExtractionField")
    ExtractionField.objects.get_or_create(
        key="issue_date",
        defaults={"label": "Data de emissao"},
    )
    ExtractionField.objects.filter(key="issue_date").update(label="Data de emissao")


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0020_document_retention"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="issue_date",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="document",
            name="due_date",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="document",
            name="document_value",
            field=models.DecimalField(
                blank=True,
                db_index=True,
                decimal_places=2,
                max_digits=14,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="juros",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=14,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="multa",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=14,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="barcode",
            field=models.CharField(blank=True, db_index=True, default="", max_length=48),
        ),
        migrations.AddField(
            model_name="document",
            name="payee_name",
            field=models.CharField(blank=True, db_index=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="document",
            name="payer_name",
            field=models.CharField(blank=True, db_index=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="document",
            name="payee_cnpj",
            field=models.CharField(blank=True, db_index=True, default="", max_length=14),
        ),
        migrations.AddField(
            model_name="document",
            name="payer_cnpj",
            field=models.CharField(blank=True, db_index=True, default="", max_length=14),
        ),
        migrations.AddField(
            model_name="document",
            name="cpf",
            field=models.CharField(blank=True, db_index=True, default="", max_length=11),
        ),
        migrations.AddField(
            model_name="document",
            name="document_number",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.RunPython(add_issue_date_field, migrations.RunPython.noop),
    ]
