"""Pola ST/MT: pegawai mendapat Surat Tugas di siang hari dan tetap dinas Malam (MT).

Jam & durasi sama dengan MT, jadi dinas malamnya tetap dihitung untuk jam kerja, uang makan
dan siapa yang bertugas (jadwal.duty).
"""
import datetime

from django.db import migrations


def add_st_mt(apps, schema_editor):
    PolaDinas = apps.get_model('jadwal', 'PolaDinas')
    PolaDinas.objects.get_or_create(kode='ST/MT', defaults=dict(
        nama='Surat Tugas + Malam',
        jam_mulai=datetime.time(19, 30),
        jam_selesai=datetime.time(8, 0),
        durasi=12.5,
        warna='#D8CC96',
        is_libur=False,
    ))


def remove_st_mt(apps, schema_editor):
    apps.get_model('jadwal', 'PolaDinas').objects.filter(kode='ST/MT', jadwalharian__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('jadwal', '0009_lapbul_file_fields'),
    ]

    operations = [
        migrations.RunPython(add_st_mt, remove_st_mt),
    ]
