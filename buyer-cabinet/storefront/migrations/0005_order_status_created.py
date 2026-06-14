import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("storefront", "0004_orders"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("CREATED", "Created"),
                    ("PAID", "Paid"),
                    ("ASSEMBLING", "Assembling"),
                    ("DELIVERING", "Delivering"),
                    ("DELIVERED", "Delivered"),
                    ("CANCELLED", "Cancelled"),
                    ("CANCEL_PENDING", "Cancel Pending"),
                ],
                default="PAID",
                max_length=20,
            ),
        ),
    ]
