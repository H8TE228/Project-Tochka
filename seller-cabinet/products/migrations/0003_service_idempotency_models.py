from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0002_quest_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProcessedRequest",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("action", models.CharField(choices=[("RESERVE", "Reserve"), ("UNRESERVE", "Unreserve")], max_length=20)),
                ("idempotency_key", models.UUIDField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="ProcessedModerationEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("idempotency_key", models.UUIDField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("sku", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="processed_moderation_events", to="products.sku")),
            ],
        ),
        migrations.AddConstraint(
            model_name="processedrequest",
            constraint=models.UniqueConstraint(fields=("action", "idempotency_key"), name="uniq_processed_request_action_idempotency"),
        ),
        migrations.AddConstraint(
            model_name="processedmoderationevent",
            constraint=models.UniqueConstraint(fields=("sku", "idempotency_key"), name="uniq_processed_moderation_event_sku_idempotency"),
        ),
    ]
