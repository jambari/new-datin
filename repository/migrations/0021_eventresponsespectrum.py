from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('repository', '0020_allow_null_tl_design_spectrum'),
    ]

    operations = [
        migrations.CreateModel(
            name='EventResponseSpectrum',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_id', models.CharField(db_index=True, max_length=100)),
                ('station_code', models.CharField(max_length=10)),
                ('component', models.CharField(help_text='e.g. EHE, EHN, EHZ', max_length=10)),
                ('latitude', models.FloatField()),
                ('longitude', models.FloatField()),
                ('distance_km', models.FloatField()),
                ('psa03', models.FloatField(help_text='PSA at T=0.3s (g)')),
                ('psa10', models.FloatField(help_text='PSA at T=1.0s (g)')),
                ('psa30', models.FloatField(help_text='PSA at T=3.0s (g)')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Event Response Spectrum',
                'verbose_name_plural': 'Event Response Spectra',
                'ordering': ['distance_km'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='eventresponsespectrum',
            unique_together={('event_id', 'station_code', 'component')},
        ),
    ]
