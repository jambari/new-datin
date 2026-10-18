from collections import Counter
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from qc_review.models import Event
from qc_review.petugas import PETUGAS_START, assign_petugas, local_time
from jadwal.duty import staff_on_duty_at


class Command(BaseCommand):
    help = "Lekatkan petugas jaga (jadwal dinas) ke event QC Repositori Angkasa sejak 1 Januari 2026."

    def add_arguments(self, parser):
        parser.add_argument("--since", help="Mulai tanggal YYYY-MM-DD (minimal 2026-01-01)")
        parser.add_argument("--refresh", action="store_true", help="Hitung ulang juga event yang sudah berpetugas")
        parser.add_argument("--dry-run", action="store_true", help="Tampilkan ringkasan tanpa menyimpan")

    def handle(self, *args, **options):
        start = PETUGAS_START
        if options["since"]:
            try:
                since = datetime.strptime(options["since"], "%Y-%m-%d").replace(tzinfo=PETUGAS_START.tzinfo)
            except ValueError:
                raise CommandError("Format --since harus YYYY-MM-DD")
            start = max(start, since)
        events = list(Event.objects.filter(origin_time__gte=start).prefetch_related("petugas"))
        if not options["refresh"]:
            events = [e for e in events if not e.petugas.all()]
        on_duty = staff_on_duty_at({local_time(e.origin_time) for e in events})
        counts = Counter(len(on_duty.get(local_time(e.origin_time), [])) for e in events)
        self.stdout.write(f"{len(events)} event sejak {start:%d/%m/%Y}; jumlah petugas per event: "
                          + ", ".join(f"{k} orang = {v}" for k, v in sorted(counts.items())))
        if options["dry_run"]:
            return
        with transaction.atomic():
            assign_petugas(events, refresh=True)
        self.stdout.write(self.style.SUCCESS(f"Petugas dilekatkan ke {len(events)} event."))
