import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("storefront", "0003_collections"),
    ]

    operations = [
        # ---- US-ORD-01: заказы ----
        migrations.CreateModel(
            name="Order",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("user_id", models.UUIDField(db_index=True)),
                ("status", models.CharField(
                    choices=[
                        ("PAID", "Paid"),
                        ("ASSEMBLING", "Assembling"),
                        ("DELIVERING", "Delivering"),
                        ("DELIVERED", "Delivered"),
                        ("CANCELLED", "Cancelled"),
                        ("CANCEL_PENDING", "Cancel Pending"),
                    ],
                    default="PAID",
                    max_length=20,
                )),
                ("total_amount", models.PositiveBigIntegerField(default=0)),
                ("delivery_address", models.TextField(blank=True, default="")),
                ("idempotency_key", models.UUIDField(unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="OrderItem",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("order", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="items",
                    to="storefront.order",
                )),
                ("sku_id", models.UUIDField()),
                ("product_id", models.UUIDField()),
                ("product_title", models.CharField(max_length=500)),
                ("sku_name", models.CharField(blank=True, default="", max_length=500)),
                ("quantity", models.PositiveIntegerField()),
                ("unit_price", models.PositiveBigIntegerField()),
                ("line_total", models.PositiveBigIntegerField()),
            ],
            options={
                "ordering": ["id"],
            },
        ),
    ]
