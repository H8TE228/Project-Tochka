import django.db.models.deletion
import django.utils.timezone
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0006_moderation_event_service_idempotency"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductModeration",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("seller_id", models.UUIDField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("IN_REVIEW", "In Review"),
                            ("MODERATED", "Moderated"),
                            ("BLOCKED", "Blocked"),
                            ("HARD_BLOCKED", "Hard Blocked"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("moderator_id", models.UUIDField(blank=True, null=True)),
                ("moderator_comment", models.TextField(blank=True, default="")),
                ("json_after", models.JSONField(default=dict)),
                ("date_created", models.DateTimeField(auto_now_add=True)),
                ("date_updated", models.DateTimeField(auto_now=True)),
                ("date_moderation", models.DateTimeField(blank=True, null=True)),
                (
                    "product",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="moderation_card",
                        to="products.product",
                    ),
                ),
            ],
            options={
                "verbose_name": "Product Moderation Card",
            },
        ),
    ]
