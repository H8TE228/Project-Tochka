import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("storefront", "0002_cart_subscriptions_banners"),
    ]

    operations = [
        # ---- US-CART-05: подборки товаров ----
        migrations.CreateModel(
            name="Collection",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("cover_image_url", models.CharField(blank=True, default="", max_length=500)),
                ("target_url", models.CharField(blank=True, default="", max_length=500)),
                ("priority", models.IntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("start_date", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-priority", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="CollectionProduct",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("collection", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="collection_products",
                    to="storefront.collection",
                )),
                ("product_id", models.UUIDField()),
                ("ordering", models.IntegerField(default=0)),
            ],
            options={
                "ordering": ["ordering"],
            },
        ),
        migrations.AddConstraint(
            model_name="collectionproduct",
            constraint=models.UniqueConstraint(
                fields=("collection", "product_id"), name="unique_collection_product"
            ),
        ),
    ]
