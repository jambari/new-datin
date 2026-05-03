"""
Compute accelerograph data availability from StationAvailabilitySample records.

Strategy: every fetch_slinktool run (~10-min intervals) writes one sample per
station with status 'on', 'gap', or 'off'.  This command counts how many of
those samples are 'on' or 'gap' for the target date and converts to a
percentage.  A station with zero samples for that date gets 0%.

--days N  : process the last N calendar days (default 5).
--backfill: for stations with no samples, fall back to slinktool ring-buffer
            coverage estimate (useful for the first 1-2 days before sampling
            was activated — the buffer does not reach further back).

Cron (runs daily at 12:00 WIT = 03:00 UTC):
  0 3 * * * /var/www/html/venv/bin/python /var/www/html/manage.py compute_accelero_availability >> /var/log/accelero_avail.log 2>&1
"""
import re
import subprocess
from datetime import date, datetime, timedelta, timezone

from django.conf import settings
from django.core.management.base import BaseCommand

from repository.models import AcceleroDataAvailability
from stations.models import Station, StationAvailabilitySample

CHANNEL_NAME = 'SLINKTOOL'
_DT_RE = re.compile(r'\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+')


def _parse_q(output):
    """Return {(net, sta): (buf_start, buf_end)} from slinktool -Q output."""
    station_map = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 6:
            continue
        qual_idx = next(
            (i for i, p in enumerate(parts) if p in ('D', 'R', 'Q', 'M') and len(p) == 1),
            None,
        )
        if qual_idx is None or qual_idx < 3:
            continue
        net, sta = parts[0], parts[1]
        dates = _DT_RE.findall(line)
        if len(dates) < 2:
            continue
        try:
            start = datetime.strptime(dates[0].strip(), '%Y/%m/%d %H:%M:%S.%f').replace(tzinfo=timezone.utc)
            end = datetime.strptime(dates[1].strip(), '%Y/%m/%d %H:%M:%S.%f').replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        key = (net, sta)
        if key not in station_map:
            station_map[key] = (start, end)
        else:
            existing_start, existing_end = station_map[key]
            station_map[key] = (min(existing_start, start), max(existing_end, end))
    return station_map


def _buffer_coverage(buf_start, buf_end, target_date):
    """Fraction of target_date (UTC) covered by [buf_start, buf_end], 0–100."""
    day_start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    if buf_end <= day_start or buf_start >= day_end:
        return 0.0
    covered = (min(buf_end, day_end) - max(buf_start, day_start)).total_seconds()
    return round(min(100.0, covered / 86400.0 * 100.0), 2)


class Command(BaseCommand):
    help = 'Compute accelerograph availability from StationAvailabilitySample records'

    def add_arguments(self, parser):
        parser.add_argument('--date', help='Target date YYYY-MM-DD; overrides --days')
        parser.add_argument(
            '--days',
            type=int,
            default=5,
            help='Number of past days to process (default: 5)',
        )
        parser.add_argument('--dry-run', action='store_true', help='Print without saving')
        parser.add_argument(
            '--backfill',
            action='store_true',
            help='Fall back to slinktool ring-buffer estimate for stations with no samples',
        )

    def handle(self, *args, **options):
        if options['date']:
            targets = [date.fromisoformat(options['date'])]
        else:
            today = date.today()
            targets = [today - timedelta(days=i) for i in range(1, options['days'] + 1)]

        # Query ring buffer once upfront if backfill is requested
        ring_map = {}
        if options['backfill']:
            host = getattr(settings, 'SEEDLINK_HOST', '202.90.199.206')
            port = getattr(settings, 'SEEDLINK_PORT', 18123)
            self.stdout.write(f'Backfill mode: querying slinktool {host}:{port}')
            try:
                result = subprocess.run(
                    ['slinktool', '-Q', f'{host}:{port}'],
                    capture_output=True, text=True, timeout=90,
                )
                ring_map = _parse_q(result.stdout)
                self.stdout.write(f'Ring buffer: {len(ring_map)} unique stations')
            except Exception as e:
                self.stderr.write(f'WARNING: slinktool failed: {e}')

        stations = list(Station.objects.filter(is_active=True))

        for target in targets:
            self._process_date(target, stations, ring_map, options)

    def _process_date(self, target, stations, ring_map, options):
        self.stdout.write(f'\n--- {target} ---')
        day_start = datetime(target.year, target.month, target.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)

        saved = skipped = backfilled = 0

        for station in stations:
            samples_qs = StationAvailabilitySample.objects.filter(
                station=station,
                sampled_at__gte=day_start,
                sampled_at__lt=day_end,
            )
            total = samples_qs.count()

            if total > 0:
                on_count = samples_qs.filter(status__in=('on', 'gap')).count()
                pct = round(on_count / total * 100.0, 2)
                method = f'samples ({on_count}/{total})'
            elif options['backfill']:
                buf = ring_map.get((station.network, station.code))
                if buf:
                    pct = _buffer_coverage(buf[0], buf[1], target)
                    if pct == 0.0:
                        self.stdout.write(f'  {station.code:6s}  ring-buffer does not reach this date — skip')
                        skipped += 1
                        continue
                    method = 'ring-buffer'
                    backfilled += 1
                else:
                    self.stdout.write(f'  {station.code:6s}  no samples, not in ring buffer — skip')
                    skipped += 1
                    continue
            else:
                self.stdout.write(f'  {station.code:6s}  no samples — skip')
                skipped += 1
                continue

            self.stdout.write(f'  {station.code:6s}  {pct:.1f}%  [{method}]')

            if not options['dry_run']:
                AcceleroDataAvailability.objects.update_or_create(
                    station=station.code,
                    channel=CHANNEL_NAME,
                    date=target,
                    defaults={'percentage': pct},
                )
                saved += 1

        if options['dry_run']:
            self.stdout.write(f'  Dry run — nothing saved.')
        else:
            self.stdout.write(self.style.SUCCESS(
                f'  Saved {saved} ({backfilled} ring-buffer, {skipped} skipped)'
            ))
