from django.db import migrations, models


class Migration(migrations.Migration):
    """
    MOD-05 arbiter feedback round 2:
    FieldReport.field_name → field_path (произвольная строка, JSONPath-подобный путь);
    FieldReport.comment → message;
    убраны choices с поля; max_length расширен под длинные JSONPath.
    Источник: moderation/openapi.yaml:756-770 FieldReport required: [field_path, message].
    """

    dependencies = [
        ("modapi", "0003_productmoderation_kind"),
    ]

    operations = [
        # Переименование сохраняет данные в существующих записях.
        migrations.RenameField(
            model_name="productmoderationfieldreport",
            old_name="field_name",
            new_name="field_path",
        ),
        migrations.RenameField(
            model_name="productmoderationfieldreport",
            old_name="comment",
            new_name="message",
        ),
        # Снимаем choices и расширяем max_length под JSONPath ('images[0].url' и т.п.).
        migrations.AlterField(
            model_name="productmoderationfieldreport",
            name="field_path",
            field=models.CharField(max_length=255),
        ),
    ]