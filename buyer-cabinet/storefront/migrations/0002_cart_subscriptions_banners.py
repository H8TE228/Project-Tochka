import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("storefront", "0001_initial"),
    ]

    operations = [
        # ---- US-CART-02: подписки ----
        migrations.CreateModel(
            name="Subscription",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("user_id", models.UUIDField()),
                ("product_id", models.UUIDField()),
                ("notify_on", models.JSONField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name="subscription",
            constraint=models.UniqueConstraint(
                fields=("user_id", "product_id"), name="unique_subscription_user_product"
            ),
        ),

        # ---- US-CART-03: корзина ----
        migrations.CreateModel(
            name="Cart",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("user_id", models.UUIDField(blank=True, db_index=True, null=True)),
                ("session_id", models.CharField(blank=True, db_index=True, max_length=128, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name="cart",
            constraint=models.UniqueConstraint(
                fields=("user_id",), condition=models.Q(user_id__isnull=False),
                name="unique_cart_per_user",
            ),
        ),
        migrations.AddConstraint(
            model_name="cart",
            constraint=models.UniqueConstraint(
                fields=("session_id",), condition=models.Q(session_id__isnull=False),
                name="unique_cart_per_session",
            ),
        ),
        migrations.CreateModel(
            name="CartItem",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("sku_id", models.UUIDField()),
                ("quantity", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("cart", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="items",
                    to="storefront.cart",
                )),
            ],
        ),
        migrations.AddConstraint(
            model_name="cartitem",
            constraint=models.UniqueConstraint(fields=("cart", "sku_id"), name="unique_cart_sku"),
        ),

        # ---- US-CART-04: баннеры ----
        migrations.CreateModel(
            name="Banner",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=200)),
                ("image_url", models.CharField(max_length=2000)),
                ("target_url", models.CharField(max_length=2000)),
                ("priority", models.IntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("starts_at", models.DateTimeField(blank=True, null=True)),
                ("ends_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="BannerEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("event_type", models.CharField(
                    choices=[("view", "View"), ("click", "Click")], max_length=16,
                )),
                ("user_id", models.UUIDField(blank=True, null=True)),
                ("session_id", models.CharField(blank=True, max_length=128, null=True)),
                ("occurred_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("banner", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="events",
                    to="storefront.banner",
                )),
            ],
        ),
    ]
