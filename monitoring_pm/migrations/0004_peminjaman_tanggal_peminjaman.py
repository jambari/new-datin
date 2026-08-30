import datetime

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitoring_pm", "0003_repair_missing_peralatan_column"),
    ]

    operations = [
        migrations.AddField(
            model_name="peminjaman",
            name="tanggal_peminjaman",
            field=models.DateField(default=datetime.date.today),
        ),
    ]
