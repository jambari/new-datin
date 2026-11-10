"""Buat peta isoseismal untuk gempa dirasakan dalam rentang tanggal (isi ulang data lama).

Sama dengan tugas per jam scan_isoseismal_task, hanya rentangnya bebas:

    python manage.py sync_isoseismal --since 2026-01-01
    python manage.py sync_isoseismal --since 2026-05-01 --until 2026-05-31
"""
import datetime

from django.core.management.base import BaseCommand, CommandError

from isoseismal.services import sync_felt


def _date(text):
    try:
        return datetime.datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        raise CommandError(f"tanggal tidak valid: {text} (format YYYY-MM-DD)")


class Command(BaseCommand):
    help = "Ambil run ShakeMap dari .50 untuk gempa dirasakan dan gambar peta isoseismalnya."

    def add_arguments(self, parser):
        parser.add_argument("--since", required=True, help="Tanggal awal UTC (YYYY-MM-DD).")
        parser.add_argument("--until", help="Tanggal akhir UTC (YYYY-MM-DD), bawaan: sekarang.")

    def handle(self, *args, **opts):
        since = _date(opts["since"])
        until = _date(opts["until"]) + datetime.timedelta(days=1) if opts["until"] else None
        lines = sync_felt(since, until)
        for line in lines:
            self.stdout.write(line)
        self.stdout.write(f"{len(lines)} kejadian diproses.")
