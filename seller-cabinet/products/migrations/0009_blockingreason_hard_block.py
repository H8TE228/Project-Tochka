from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0008_productmoderation_kind_queue_priority"),
    ]

    operations = [
        migrations.AddField(
            model_name="blockingreason",
            name="hard_block",
            field=models.BooleanField(default=False),
        ),
    ]
