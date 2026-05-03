"""
Backfill AcceleroDataAvailability for a specific date by fetching actual
MiniSEED packet coverage from the SeedLink server (time-window mode).

For each station, queries slinktool -S 'NET_STA:HNN' -tw 'begin:end' -p
and sums (samples / sample_rate) to get total seconds of real data, then
divides by 86400 to get the availability percentage.

Usage:
  python manage.py backfill_accelero_from_seedlink --date 2026-05-03
  python manage.py backfill_accelero_from_seedlink --date 2026-05-03 --dry-run
"""
import re
import subprocess
from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand

from repository.models import AcceleroDataAvailability
from stations.models import Station

CHANNEL = 'HNN'
CHANNEL_NAME = 'SLINKTOOL'
_RECORD_RE = re.compile(
    r'[\w_]+,\s*(\d+)\s*samples,\s*([\d.]+)\s*Hz'
)


def _seedlink_coverage(host, port, network, sta_code, target_date):
    """
    Return seconds of HNN data present on the SeedLink server for target_date (UTC).
    Returns None if slinktool fails.
    """
    begin = target_date.strftime('%Y,%m,%d,00,00,00')
    next_day = target_date + timedelta(days=1)
    end = next_day.strftime('%Y,%m,%d,00,00,00')

    stream = f'{network}_{sta_code}:{CHANNEL}'
    server = f'{host}:{port}'

    try:
        result = subprocess.run(
            ['slinktool', '-S', stream, '-tw', f'{begin}:{end}', '-p', server],
            capture_output=True, text=True, timeout=120,
        )
        output = result.stdout
    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None

    total_seconds = 0.0
    for line in output.splitlines():
        m = _RECORD_RE.search(line)
        if m:
            samples = int(m.group(1))
            hz = float(m.group(2))
            if hz > 0:
                total_seconds += samples / hz

    return min(total_seconds, 86400.0)


class Command(BaseCommand):
    help = 'Backfill accelero availability for a date from SeedLink time-window data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            required=True,
            help='Target date YYYY-MM-DD',
        )
        parser.add_argument('--dry-run', action='store_true', help='Print without saving')

    def handle(self, *args, **options):
        target = date.fromisoformat(options['date'])
        host = getattr(settings, 'SEEDLINK_HOST', '202.90.199.206')
        port = getattr(settings, 'SEEDLINK_PORT', 18123)

        self.stdout.write(f'Backfilling {target} from {host}:{port} (channel {CHANNEL})')

        stations = Station.objects.filter(is_active=True)
        saved = skipped = 0

        for station in stations:
            self.stdout.write(f'  {station.code:6s} ... ', ending='')
            self.stdout.flush()

            seconds = _seedlink_coverage(host, port, station.network, station.code, target)

            if seconds is None:
                self.stdout.write('ERROR (slinktool failed)')
                skipped += 1
                continue

            pct = round(seconds / 86400.0 * 100.0, 2)
            self.stdout.write(f'{seconds:.0f}s  →  {pct:.1f}%')

            if not options['dry_run']:
                AcceleroDataAvailability.objects.update_or_create(
                    station=station.code,
                    channel=CHANNEL_NAME,
                    date=target,
                    defaults={'percentage': pct},
                )
                saved += 1
            else:
                skipped += 1

        if options['dry_run']:
            self.stdout.write('Dry run — nothing saved.')
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Done. Saved {saved}, skipped {skipped}.'
            ))
