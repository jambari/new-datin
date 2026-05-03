"""
Compute accelerograph data availability from StationAvailabilitySample records.

Strategy: every fetch_slinktool run (~10-min intervals) writes one sample per
station with status 'on', 'gap', or 'off'.  This command counts how many of
those samples are 'on' or 'gap' for the target date and converts to a
percentage.  A station with zero samples for that date gets 0%.

Run daily at 12:00 WIT (03:00 UTC) so the previous UTC day is fully sampled.

Cron (add to /etc/crontab on production):
  0 3 * * * /var/www/html/venv/bin/python /var/www/html/manage.py compute_accelero_availability >> /var/log/accelero_avail.log 2>&1
"""
from datetime import date, datetime, timedelta, timezone

from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from repository.models import AcceleroDataAvailability
from stations.models import Station, StationAvailabilitySample

CHANNEL_NAME = 'SLINKTOOL'


class Command(BaseCommand):
    help = 'Compute accelerograph availability from StationAvailabilitySample records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            help='Target date YYYY-MM-DD (default: yesterday UTC)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print results without saving to database',
        )

    def handle(self, *args, **options):
        if options['date']:
            target = date.fromisoformat(options['date'])
        else:
            target = date.today() - timedelta(days=1)

        self.stdout.write(f'[compute_accelero_availability] target date: {target}')

        day_start = datetime(target.year, target.month, target.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)

        stations = Station.objects.filter(is_active=True).prefetch_related('samples')

        saved = skipped = 0
        for station in stations:
            samples_qs = StationAvailabilitySample.objects.filter(
                station=station,
                sampled_at__gte=day_start,
                sampled_at__lt=day_end,
            )
            total = samples_qs.count()
            if total == 0:
                self.stdout.write(f'  {station.code:6s}  no samples — skip')
                skipped += 1
                continue

            on_count = samples_qs.filter(status__in=('on', 'gap')).count()
            pct = round(on_count / total * 100.0, 2)

            self.stdout.write(f'  {station.code:6s}  {on_count}/{total} samples  {pct:.1f}%')

            if not options['dry_run']:
                AcceleroDataAvailability.objects.update_or_create(
                    station=station.code,
                    channel=CHANNEL_NAME,
                    date=target,
                    defaults={'percentage': pct},
                )
                saved += 1

        if options['dry_run']:
            self.stdout.write('Dry run — nothing saved.')
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Saved {saved} records for {target} ({skipped} skipped — no samples)'
            ))
