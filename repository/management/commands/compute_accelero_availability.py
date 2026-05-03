"""
Compute accelerograph data availability from SeedLink ring buffer.

Strategy: query `slinktool -Q` to get each stream's buffer start/end time.
Availability for a target date = seconds of that date covered by the buffer / 86400 * 100.
This is an approximation that assumes continuous streaming within the buffer window.

Run daily at 12:00 WIT (03:00 UTC) so the previous UTC day is fully elapsed.

Cron (add to /etc/crontab on production):
  0 3 * * * /var/www/html/venv/bin/python /var/www/html/manage.py compute_accelero_availability >> /var/log/accelero_avail.log 2>&1
"""
import re
import subprocess
from datetime import date, datetime, timedelta, timezone

from django.core.management.base import BaseCommand

from repository.models import AcceleroDataAvailability

SEEDLINK_SERVER = '202.90.199.206:18123'

STATIONS = [
    'ARKPI', 'ARPI', 'BMPI', 'BTSPI', 'DYPI', 'EDMPI', 'ELMPI', 'FKMPM',
    'GENI', 'JBPI', 'JGPI', 'JMPI', 'KIMPI', 'LJPI', 'MIBPI', 'MMPI',
    'MTJPI', 'MTMPI', 'OBMPI', 'SATPI', 'SKPM', 'SMPI', 'SOMPI', 'TMPI',
    'TRPI', 'WAMI',
]

CHANNELS = ['HNE', 'HNN', 'HNZ']

_DT_RE = re.compile(r'\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+')


def _parse_q_output(output):
    """Return {(net, sta, chan): {'start': datetime, 'end': datetime}} from slinktool -Q."""
    streams = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 7:
            continue

        # Locate quality flag (single char D/R/Q/M) to anchor channel position
        qual_idx = next(
            (i for i, p in enumerate(parts) if p in ('D', 'R', 'Q', 'M') and len(p) == 1),
            None,
        )
        if qual_idx is None or qual_idx < 3:
            continue

        net = parts[0]
        sta = parts[1]
        chan = parts[qual_idx - 1]

        dates = _DT_RE.findall(line)
        if len(dates) < 2:
            continue

        try:
            start = datetime.strptime(dates[0].strip(), '%Y/%m/%d %H:%M:%S.%f').replace(tzinfo=timezone.utc)
            end = datetime.strptime(dates[1].strip(), '%Y/%m/%d %H:%M:%S.%f').replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        streams[(net, sta, chan)] = {'start': start, 'end': end}

    return streams


def _buffer_availability(buf_start, buf_end, target_date):
    """Fraction of target_date (UTC) covered by [buf_start, buf_end], as 0–100."""
    day_start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    if buf_end <= day_start or buf_start >= day_end:
        return 0.0

    covered = (min(buf_end, day_end) - max(buf_start, day_start)).total_seconds()
    return round(min(100.0, covered / 86400.0 * 100.0), 2)


class Command(BaseCommand):
    help = 'Compute accelerograph availability from SeedLink ring buffer for a given date'

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

        try:
            result = subprocess.run(
                ['slinktool', '-Q', SEEDLINK_SERVER],
                capture_output=True, text=True, timeout=90,
            )
            output = result.stdout
        except subprocess.TimeoutExpired:
            self.stderr.write('ERROR: slinktool -Q timed out')
            return
        except Exception as e:
            self.stderr.write(f'ERROR: {e}')
            return

        if not output.strip():
            self.stderr.write('ERROR: no output from slinktool -Q')
            return

        streams = _parse_q_output(output)
        self.stdout.write(f'Ring buffer: {len(streams)} streams found')

        saved = 0
        for sta in STATIONS:
            for chan in CHANNELS:
                info = streams.get(('IA', sta, chan))
                pct = _buffer_availability(info['start'], info['end'], target) if info else 0.0

                tag = f'{pct:.1f}%' if info else '0.0% (no stream)'
                self.stdout.write(f'  {sta:6s} {chan}  {tag}')

                if not options['dry_run']:
                    AcceleroDataAvailability.objects.update_or_create(
                        station=sta,
                        channel=chan,
                        date=target,
                        defaults={'percentage': pct},
                    )
                    saved += 1

        if options['dry_run']:
            self.stdout.write('Dry run — nothing saved.')
        else:
            self.stdout.write(self.style.SUCCESS(f'Saved {saved} records for {target}'))
