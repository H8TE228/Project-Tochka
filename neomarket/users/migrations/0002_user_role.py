

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='role',
            field=models.CharField(choices=[('admin', 'Admin'), ('client', 'Client'), ('moderator', 'Moderator'), ('seller', 'Seller')], default='client', max_length=20),
        ),
    ]

