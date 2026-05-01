from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0001_initial"),
    ]

    operations = [
        # Справочник причин блокировки (US-B2B-05)
        migrations.CreateModel(
            name="BlockingReason",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=500)),
            ],
        ),

        # HARD_BLOCKED — пятый статус (US-B2B-02, US-B2B-03)
        migrations.AlterField(
            model_name="product",
            name="status",
            field=models.CharField(
                choices=[
                    ("CREATED", "Created"),
                    ("ON_MODERATION", "On Moderation"),
                    ("MODERATED", "Moderated"),
                    ("BLOCKED", "Blocked"),
                    ("HARD_BLOCKED", "Hard Blocked"),
                ],
                default="CREATED",
                max_length=20,
            ),
        ),

        # Новые поля Product (US-B2B-04, US-B2B-05)
        migrations.AddField(
            model_name="product",
            name="deleted",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="product",
            name="blocking_reason",
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="products",
                to="products.blockingreason",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="moderator_comment",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="product",
            name="field_reports",
            field=models.JSONField(blank=True, default=list),
        ),

        # SKU: переименовать price_cents -> price (по канон-flow B2B-2)
        migrations.RenameField(
            model_name="sku",
            old_name="price_cents",
            new_name="price",
        ),

        # SKU: новые поля (US-B2B-02, US-B2B-03)
        migrations.AddField(
            model_name="sku",
            name="cost_price",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="sku",
            name="discount",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="sku",
            name="reserved_quantity",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="sku",
            name="image",
            field=models.CharField(default="", max_length=2000),
        ),
    ]