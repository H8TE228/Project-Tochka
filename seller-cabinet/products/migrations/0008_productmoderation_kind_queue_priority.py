from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0007_product_moderation"),
    ]

    operations = [
        migrations.AddField(
            model_name="productmoderation",
            name="kind",
            field=models.CharField(default="PRODUCT", max_length=50),
        ),
        migrations.AddField(
            model_name="productmoderation",
            name="queue_priority",
            field=models.IntegerField(default=1),
        ),
    ]
