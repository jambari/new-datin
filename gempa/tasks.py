"""Task Celery untuk peta GMT.

Dipanggil otomatis oleh signal saat ada event katalog baru (gempa/signals.py),
dan bisa juga dipanggil manual dari shell. Isinya tipis: memanggil management
command yang sama dengan yang dipakai operator dari CLI.
"""
import logging

from celery import shared_task
from django.core.management import call_command

logger = logging.getLogger(__name__)


@shared_task(autoretry_for=(Exception,),
             retry_kwargs={'max_retries': 2, 'countdown': 120},
             retry_backoff=True)
def generate_gmt_map_task(region, pk, force=False):
    """Buat peta GMT untuk satu event katalog.

    Retry 2x dengan jeda 2 menit: render GMT bisa gagal sementara (CPU penuh),
    dan kalau berkasnya sudah terbuat, panggilan ulang hanya akan dilewat.
    """
    logger.info('GMT: membuat peta region=%s pk=%s (force=%s)', region, pk, force)
    call_command('buat_peta_gmt', region, pk=pk, force=force)
    logger.info('GMT: selesai region=%s pk=%s', region, pk)
