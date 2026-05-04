"""
Backfill AcceleroDataAvailability for specific dates by fetching real
MiniSEED data from the FDSNWS dataselect endpoint and computing actual
sample coverage.

Parses MiniSEED record headers (struct) to sum (samples / sample_rate)
per station per day, giving true availability without needing obspy.

Usage:
  python manage.py backfill_accelero_from_fdsnws --date 2026-05-03
  python manage.py backfill_accelero_from_fdsnws --date 2026-05-01 --dry-run
"""
import struct
from datetime import date, timedelta

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from repository.models import AcceleroDataAvailability
from stations.models import Station

FDSNWS_URL = getattr(settings, 'FDSNWS_URL', 'http://172.21.63.51:8080')
CHANNEL = 'HNN'
CHANNEL_NAME = 'SLINKTOOL'
RECORD_SIZE = 512  # bytes, standard SeisComP MiniSEED record length


def _sample_rate(factor, multiplier):
    if factor > 0 and multiplier > 0:
        return float(factor * multiplier)
    if factor > 0 and multiplier < 0:
        return -float(factor) / multiplier
    if factor < 0 and multiplier > 0:
        return -float(multiplier) / factor
    if factor < 0 and multiplier < 0:
        return 1.0 / (factor * multiplier)
    return 0.0


def _parse_mseed_seconds(data):
    """Parse raw MiniSEED bytes and return total seconds of data coverage."""
    total = 0.0
    pos = 0
    while pos + RECORD_SIZE <= len(data):
        hdr = data[pos:pos + 48]
        if len(hdr) < 48:
            break
        num_samples = struct.unpack('>H', hdr[30:32])[0]
        factor = struct.unpack('>h', hdr[32:34])[0]
        multiplier = struct.unpack('>h', hdr[34:36])[0]
        rate = _sample_rate(factor, multiplier)
        if rate > 0 and num_samples > 0:
            total += num_samples / rate
        pos += RECORD_SIZE
    return total


def _fetch_coverage(network, station_code, target_date):
    """
    Return seconds of HNN data from FDSNWS dataselect for target_date (UTC).
    Returns None on HTTP error.
    """
    start = target_date.strftime('%Y-%m-%dT00:00:00')
    end = (target_date + timedelta(days=1)).strftime('%Y-%m-%dT00:00:00')
    url = (
        f'{FDSNWS_URL}/fdsnws/dataselect/1/query'
        f'?network={network}&station={station_code}'
        f'&channel={CHANNEL}&start={start}&end={end}'
    )
    try:
        resp = requests.get(url, timeout=120, stream=True)
        if resp.status_code == 204 or resp.status_code == 404:
            return 0.0
        if resp.status_code != 200:
            return None
        data = resp.content
        return _parse_mseed_seconds(data)
    except Exception:
        return None


class Command(BaseCommand):
    help = 'Backfill accelero availability from FDSNWS dataselect (172.21.63.51:8080)'

    def add_arguments(self, parser):
        parser.add_argument('--date', required=True, help='Target date YYYY-MM-DD')
        parser.add_argument('--dry-run', action='store_true', help='Print without saving')

    def handle(self, *args, **options):
        target = date.fromisoformat(options['date'])
        self.stdout.write(f'Backfilling {target} from {FDSNWS_URL} (channel {CHANNEL})')

        stations = Station.objects.filter(is_active=True)
        saved = skipped = 0

        for station in stations:
            self.stdout.write(f'  {station.code:6s} ... ', ending='')
            self.stdout.flush()

            seconds = _fetch_coverage(station.network, station.code, target)

            if seconds is None:
                self.stdout.write('ERROR (request failed)')
                skipped += 1
                continue

            pct = round(min(seconds, 86400.0) / 86400.0 * 100.0, 2)
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
            self.stdout.write(self.style.SUCCESS(f'Done. Saved {saved}, skipped {skipped}.'))
