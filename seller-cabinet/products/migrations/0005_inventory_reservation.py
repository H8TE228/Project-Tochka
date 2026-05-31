from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0004_invoice_status_accepted_quantity"),
    ]

    operations = [
        migrations.CreateModel(
            name="InventoryReservation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("order_id", models.UUIDField(db_index=True)),
                ("quantity", models.IntegerField()),
                ("reserved_at", models.DateTimeField(auto_now_add=True)),
                (
                    "sku",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inventory_reservations",
                        to="products.sku",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="inventoryreservation",
            constraint=models.UniqueConstraint(
                fields=("order_id", "sku"),
                name="uniq_inventory_reservation_order_sku",
            ),
        ),
    ]
