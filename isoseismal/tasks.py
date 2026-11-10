"""Tugas Celery peta isoseismal."""
import datetime

from celery import shared_task
from django.utils import timezone

from .models import IsoseismalMap
from .services import generate

SCAN_DAYS = 7                     # laporan dirasakan BMKG/katalog bisa datang belakangan


@shared_task
def generate_isoseismal_task(wib_id, force=False):
    """Gambar peta isoseismal satu kejadian (dipanggil setelah ingest dari .50)."""
    obj = IsoseismalMap.objects.filter(wib_id=wib_id).first()
    if obj is None:
        return f'{wib_id}: tidak ada data ShakeMap'
    return f'{wib_id}: {generate(obj, force=force)}'


@shared_task
def scan_isoseismal_task(days=SCAN_DAYS):
    """Periksa kejadian beberapa hari terakhir: gambar bila laporan dirasakan baru masuk/berubah."""
    since = timezone.now() - datetime.timedelta(days=days)
    out = []
    for obj in IsoseismalMap.objects.filter(event_time__gte=since):
        status = generate(obj)
        if not status.startswith('skip'):
            out.append(f'{obj.wib_id}: {status}')
    return out
