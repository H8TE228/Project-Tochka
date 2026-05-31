from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0005_inventory_reservation"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="processedmoderationevent",
            name="uniq_processed_moderation_event_sku_idempotency",
        ),
        migrations.RemoveField(
            model_name="processedmoderationevent",
            name="sku",
        ),
        migrations.AddField(
            model_name="processedmoderationevent",
            name="service_id",
            field=models.CharField(default="legacy", max_length=128),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name="processedmoderationevent",
            constraint=models.UniqueConstraint(
                fields=("service_id", "idempotency_key"),
                name="uniq_processed_moderation_event_service_idempotency",
            ),
        ),
    ]
