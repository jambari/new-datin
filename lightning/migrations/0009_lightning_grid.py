# Generated manually to satisfy dependency chain

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lightning', '0008_lightningdataavailability'),
    ]

    operations = [
        migrations.CreateModel(
            name='LightningGrid',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ],
        ),
    ]
