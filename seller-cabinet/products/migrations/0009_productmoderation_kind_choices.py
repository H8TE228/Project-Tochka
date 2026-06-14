from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0008_productmoderation_kind_queue_priority"),
    ]

    operations = [
        migrations.AlterField(
            model_name="productmoderation",
            name="kind",
            field=models.CharField(
                choices=[("CREATE", "Create"), ("EDIT", "Edit")],
                default="CREATE",
                max_length=50,
            ),
        ),
    ]
