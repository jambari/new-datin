"""
Compute daily seismic data availability from the SDS archive on scproc.

The station-QC job on scproc (scripts/station_qc/station_qc.py) measures, per
channel and UTC day, how much of the day is in the SDS archive and posts it to
qc_review.StationDailyQC (metrics.availability_pct). This command turns that
into one value per seismic station and day and writes it to
repository.DataAvailability with channel='SLINKTOOL' (the name the
availability matrix already uses for the machine value).

Only seismometer channels count: instrument code 'H' (SH?, BH?, HH?), so the
HN? channels of colocated accelerographs are ignored. Per station the
components of one location+band are averaged and the best group is taken.

The status samples (StationAvailabilitySample) are NOT used: they are shared
with the accelerograph SeedLink feed for colocated stations, so a seismic
station looked "off" whenever its accelerograph was missing from that feed.

Days for which scproc has not posted yet are skipped (nothing is overwritten).
A seismic station absent from an already-posted day is written as 0%.

--days N  : process the last N calendar days (default 5).
--date    : process a single date YYYY-MM-DD (overrides --days).
--dry-run : print without saving.

Cron (prod, runs daily at 03:10 UTC; the scproc job posts at 01:40 UTC):
  10 3 * * * /var/www/html/venv/bin/python /var/www/html/manage.py compute_seismic_availability >> /var/log/seismic_avail.log 2>&1
"""
from collections import defaultdict
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from qc_review.models import StationDailyQC
from repository.models import DataAvailability
from stations.constants import SEISMIC_STATIONS
from stations.models import Station

CHANNEL_NAME = 'SLINKTOOL'


def station_availability(rows):
    """Best location+band group average of seismometer channels, or None.

    rows: iterable of (location, channel, metrics) for one station-day.
    """
    groups = defaultdict(list)
    for loc, cha, metrics in rows:
        if len(cha) != 3 or cha[1] != 'H':
            continue
        groups[(loc, cha[0])].append(float((metrics or {}).get('availability_pct') or 0.0))
    if not groups:
        return None
    return round(max(sum(v) / len(v) for v in groups.values()), 2)


class Command(BaseCommand):
    help = 'Compute seismic availability from the SDS archive (qc_review StationDailyQC)'

    def add_arguments(self, parser):
        parser.add_argument('--date', help='Target date YYYY-MM-DD; overrides --days')
        parser.add_argument(
            '--days',
            type=int,
            default=5,
            help='Number of past days to process (default: 5)',
        )
        parser.add_argument('--dry-run', action='store_true', help='Print without saving')

    def handle(self, *args, **options):
        if options['date']:
            targets = [date.fromisoformat(options['date'])]
        else:
            today = date.today()
            targets = [today - timedelta(days=i) for i in range(1, options['days'] + 1)]

        networks = dict(
            Station.objects.filter(code__in=SEISMIC_STATIONS, station_type='seismic')
            .values_list('code', 'network')
        )
        for target in sorted(targets):
            self._process_date(target, networks, options)

    def _process_date(self, target, networks, options):
        self.stdout.write(f'\n--- {target} ---')
        if not StationDailyQC.objects.filter(day=target).exists():
            self.stdout.write('  no SDS data posted from scproc for this day — skip')
            return

        by_station = defaultdict(list)
        for net, sta, loc, cha, metrics in (
                StationDailyQC.objects.filter(day=target, station__in=SEISMIC_STATIONS)
                .values_list('network', 'station', 'location', 'channel', 'metrics')):
            if net == networks.get(sta, 'IA'):
                by_station[sta].append((loc, cha, metrics))

        saved = 0
        for code in SEISMIC_STATIONS:
            pct = station_availability(by_station.get(code, []))
            if pct is None:
                pct, note = 0.0, 'not in archive'
            else:
                note = 'SDS'
            self.stdout.write(f'  {code:6s}  {pct:6.2f}%  [{note}]')
            if not options['dry_run']:
                DataAvailability.objects.update_or_create(
                    station=code,
                    channel=CHANNEL_NAME,
                    date=target,
                    defaults={'percentage': pct},
                )
                saved += 1

        if options['dry_run']:
            self.stdout.write('  Dry run — nothing saved.')
        else:
            self.stdout.write(self.style.SUCCESS(f'  Saved {saved}'))
