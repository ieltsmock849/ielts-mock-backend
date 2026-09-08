from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_alter_user_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='plain_password',
            field=models.CharField(max_length=128, blank=True, default=''),
        ),
    ]