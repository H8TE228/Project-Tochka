from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0003_service_idempotency_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="sku",
            name="deleted",
            field=models.BooleanField(default=False),
        ),
    ]
