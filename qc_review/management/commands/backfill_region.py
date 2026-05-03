"""
Backfill Event.region and QCRun.snap_region using nearest ReferenceLocation.

Usage:
    python manage.py backfill_region           # semua event
    python manage.py backfill_region --dry-run # preview tanpa simpan
"""
from django.core.management.base import BaseCommand

from qc_review.models import Event
from repository.utils import calculate_remark


class Command(BaseCommand):
    help = "Backfill region dari nearest city untuk semua QC Event"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Tampilkan perubahan tanpa menyimpan ke database",
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]
        events = Event.objects.prefetch_related("runs").all()
        total = events.count()
        self.stdout.write(f"Total event: {total}" + (" [DRY RUN]" if dry else ""))

        updated_events = 0
        updated_runs = 0

        for ev in events:
            if ev.latitude is None or ev.longitude is None:
                continue

            new_region = calculate_remark(ev.latitude, ev.longitude)
            if not new_region:
                continue

            old_region = ev.region or ""
            if old_region != new_region:
                self.stdout.write(
                    f"  [{ev.public_id}] {old_region!r} → {new_region!r}"
                )
                if not dry:
                    ev.region = new_region
                    ev.save(update_fields=["region"])
                updated_events += 1

            for run in ev.runs.all():
                if run.snap_region != new_region:
                    if not dry:
                        run.snap_region = new_region
                        run.save(update_fields=["snap_region"])
                    updated_runs += 1

        action = "Akan diupdate" if dry else "Diupdate"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action}: {updated_events} event, {updated_runs} run snapshot"
            )
        )
