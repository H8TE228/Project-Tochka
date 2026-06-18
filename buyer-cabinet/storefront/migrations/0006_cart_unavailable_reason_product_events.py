import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("storefront", "0005_order_status_created"),
    ]

    operations = [
        migrations.AddField(
            model_name="cartitem",
            name="unavailable_reason",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.CreateModel(
            name="ProcessedProductEvent",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("idempotency_key", models.UUIDField(unique=True)),
                ("event", models.CharField(max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
