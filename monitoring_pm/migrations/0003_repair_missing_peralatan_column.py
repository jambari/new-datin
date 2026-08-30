from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("monitoring_pm", "0002_alter_peralatan_status"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE monitoring_pm_peminjaman
                ADD COLUMN IF NOT EXISTS peralatan jsonb NOT NULL DEFAULT '[]'::jsonb;
            """,
            reverse_sql="""
                ALTER TABLE monitoring_pm_peminjaman
                DROP COLUMN IF EXISTS peralatan;
            """,
        ),
    ]
