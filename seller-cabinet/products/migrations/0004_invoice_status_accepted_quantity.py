from django.db import migrations, models


class Migration(migrations.Migration):
    """US-B2B-06: Invoice.status, Invoice.updated_at, InvoiceLine.accepted_quantity."""

    dependencies = [
        ("products", "0003_service_idempotency_models"),
    ]

    operations = [
        # Invoice: статус накладной по спецификации OpenAPI
        migrations.AddField(
            model_name="invoice",
            name="status",
            field=models.CharField(
                choices=[
                    ("CREATED", "Created"),
                    ("PARTIALLY_ACCEPTED", "Partially Accepted"),
                    ("ACCEPTED", "Accepted"),
                    ("CANCELLED", "Cancelled"),
                ],
                default="CREATED",
                max_length=20,
            ),
        ),
        # Invoice: updated_at (требуется в InvoiceResponse по OpenAPI)
        migrations.AddField(
            model_name="invoice",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        # InvoiceLine: фактически принятое количество (заполняется при приёмке)
        migrations.AddField(
            model_name="invoiceline",
            name="accepted_quantity",
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
