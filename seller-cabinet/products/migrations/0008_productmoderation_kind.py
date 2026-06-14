from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0007_product_moderation"),
    ]

    operations = [
        migrations.AddField(
            model_name="productmoderation",
            name="kind",
            field=models.CharField(
                choices=[("CREATE", "Create"), ("EDIT", "Edit")],
                default="CREATE",
                max_length=50,
            ),
        ),
    ]
