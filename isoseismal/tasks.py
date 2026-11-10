"""Tugas Celery peta isoseismal."""
import datetime

from celery import shared_task
from django.utils import timezone

from .services import sync_felt

SCAN_DAYS = 7                     # laporan dirasakan BMKG/katalog bisa datang belakangan


@shared_task
def scan_isoseismal_task(days=SCAN_DAYS):
    """Gempa dirasakan beberapa hari terakhir: ambil run ShakeMap-nya dari .50 bila baru/berubah,
    lalu gambar peta (atau gambar ulang bila laporan dirasakan berubah)."""
    return sync_felt(timezone.now() - datetime.timedelta(days=days))
