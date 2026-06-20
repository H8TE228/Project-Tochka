from django.db import migrations, models


class Migration(migrations.Migration):
    """MOD-05 arbiter fix: kind должно быть enum [CREATE, EDIT] по moderation/openapi.yaml:646-648."""

    dependencies = [
        ("products", "0009_blockingreason_hard_block"),
    ]

    operations = [
        # Сначала переименовываем устаревшее значение 'PRODUCT' → 'CREATE' (бэкфилл).
        migrations.RunSQL(
            sql="UPDATE products_productmoderation SET kind = 'CREATE' WHERE kind = 'PRODUCT';",
            reverse_sql="UPDATE products_productmoderation SET kind = 'PRODUCT' WHERE kind = 'CREATE';",
        ),
        migrations.AlterField(
            model_name="productmoderation",
            name="kind",
            field=models.CharField(
                choices=[("CREATE", "Create"), ("EDIT", "Edit")],
                default="CREATE",
                max_length=10,
            ),
        ),
    ]