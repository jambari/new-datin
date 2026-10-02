"""Signal: buat peta GMT otomatis saat ada event katalog baru.

Di .188 peta dibuat saat `ingest_gempa` memasukkan/memperbarui event. Di .189
tidak ada feed SeisComp, jadi pemicunya adalah penyimpanan event baru — dari
admin, form, management command, atau API.

BULK IMPORT: `load_katalog` memakai `loaddata`, dan loaddata memanggil save()
per objek — artinya 113.000 event akan memicu 113.000 render GMT. Karena itu
sinkronisasi dibungkus `gmt_generation_suspended()`. Sebagai jaring pengaman
kedua, `gmt.generate()` tidak melakukan apa-apa kalau berkas petanya sudah ada
(dan peta arsip memang sudah disalin dari .188).
"""
import logging
from contextlib import contextmanager

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from . import gmt
from .models import Balaigempa, Gempa, Gempanabire, Gempasorong

logger = logging.getLogger(__name__)

#: True selama operasi massal (loaddata) berlangsung.
_suspended = False


@contextmanager
def gmt_generation_suspended():
    """Matikan pembuatan peta otomatis selama blok ini (dipakai load_katalog)."""
    global _suspended
    previous = _suspended
    _suspended = True
    try:
        yield
    finally:
        _suspended = previous


def _region_for(sender):
    for region, model_name in gmt.REGION_MODEL.items():
        if sender.__name__ == model_name:
            return region
    return None


def _queue_map(sender, instance, created=False, **kwargs):
    """Queue satu task pembuatan peta untuk event yang BARU dibuat.

    Update tidak memicu render (mahal, dan berkasnya biasanya sudah ada).
    Untuk menyegarkan peta setelah koreksi koordinat, pakai tombol
    "Buat ulang peta GMT" di halaman press/template.
    """
    if not created:
        return
    if _suspended:
        return
    if not getattr(settings, 'GMT_ENABLED', True):
        return
    region = _region_for(sender)
    if region is None:
        return

    # Tanpa data lengkap, buat_peta.sh akan menghasilkan peta yang salah.
    required = ('lintang', 'bujur', 'magnitudo', 'depth', 'tanggal', 'origin')
    missing = [f for f in required if getattr(instance, f, None) in (None, '')]
    if missing:
        logger.info('GMT dilewati untuk %s pk=%s: data kurang %s',
                    sender.__name__, instance.pk, missing)
        return

    from .tasks import generate_gmt_map_task

    pk = instance.pk
    # after commit: jangan buat peta untuk baris yang ternyata di-rollback
    def _enqueue():
        # Broker sedang mati bukan alasan menggagalkan penyimpanan event.
        try:
            generate_gmt_map_task.delay(region, pk)
        except Exception as exc:              # noqa: BLE001
            logger.warning('GMT tidak bisa dijadwalkan untuk %s pk=%s: %s',
                           sender.__name__, pk, exc)

    transaction.on_commit(_enqueue)
    logger.info('GMT dijadwalkan untuk %s pk=%s (region %s)', sender.__name__, pk, region)


# Satu receiver per model, dengan dispatch_uid agar tidak terdaftar dua kali.
for _model in (Gempa, Balaigempa, Gempasorong, Gempanabire):
    post_save.connect(
        _queue_map,
        sender=_model,
        dispatch_uid=f'gempa.gmt_on_save.{_model.__name__}',
    )
