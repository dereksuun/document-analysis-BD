from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0008_payer_payee_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="extracted_text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="document",
            name="ocr_used",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="document",
            name="text_quality",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
