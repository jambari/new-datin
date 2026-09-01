"""
Fetch real-time station status from SeedLink via slinktool -Q.
Updates StationStatus for every Station of the given type.

Usage:
  python manage.py fetch_slinktool --type accelero   (default)
  python manage.py fetch_slinktool --type seismic

Cron (add to /etc/crontab on production):
  */10 * * * * cd /var/www/html && venv/bin/python manage.py fetch_slinktool --type accelero >> /var/log/fetch_slinktool_accelero.log 2>&1
  */10 * * * * cd /var/www/html && venv/bin/python manage.py fetch_slinktool --type seismic  >> /var/log/fetch_slinktool_seismic.log  2>&1
"""
import re
import subprocess
from datetime import datetime, timezone

from django.conf import settings
from django.core.management.base import BaseCommand

from stations.models import Station, StationStatus, StationAvailabilitySample

SEISMIC_CHANNELS  = ['BHZ', 'BHN', 'BHE', 'HHZ', 'HHN', 'HHE', 'SHZ', 'SHN', 'SHE', 'EHZ', 'EHN', 'EHE']
ACCELERO_CHANNELS = ['HNN', 'HNE', 'HNZ', 'HLN', 'HLE', 'HLZ', 'BHN', 'BHE', 'BHZ']

_DT_RE = re.compile(r'\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+')


def _parse_q(output, priority_channels):
    """Return {(net, sta): {'channel', 'latency', 'last_packet'}} from slinktool -Q output."""
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

        net = parts[0]
        sta = parts[1]
        cha = parts[qual_idx - 1]

        dates = _DT_RE.findall(line)
        if len(dates) < 2:
            continue

        try:
            end_time = datetime.strptime(dates[1].strip(), '%Y/%m/%d %H:%M:%S.%f').replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        latency = max(0.0, (datetime.now(timezone.utc) - end_time).total_seconds())
        key = (net, sta)
        existing = station_map.get(key)

        if existing is None:
            station_map[key] = {'channel': cha, 'latency': latency, 'last_packet': end_time}
        else:
            ep = priority_channels.index(existing['channel']) if existing['channel'] in priority_channels else 99
            np_ = priority_channels.index(cha) if cha in priority_channels else 99
            if np_ < ep:
                station_map[key] = {'channel': cha, 'latency': latency, 'last_packet': end_time}

    return station_map


class Command(BaseCommand):
    help = 'Fetch station status from SeedLink via slinktool -Q and update StationStatus'

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            dest='station_type',
            choices=['seismic', 'accelero'],
            default='accelero',
            help='Station type to update (seismic → 202.90.198.101:18000, accelero → 202.90.199.206:18123)',
        )

    def handle(self, *args, **options):
        stype = options['station_type']

        from stations.constants import ACCELEROGRAPH_STATIONS, SEISMIC_STATIONS
        if stype == 'seismic':
            host = getattr(settings, 'SEISMIC_SEEDLINK_HOST', '202.90.198.101')
            port = getattr(settings, 'SEISMIC_SEEDLINK_PORT', 18000)
            priority_channels = SEISMIC_CHANNELS
            roster = SEISMIC_STATIONS
        else:
            host = getattr(settings, 'SEEDLINK_HOST', '202.90.199.206')
            port = getattr(settings, 'SEEDLINK_PORT', 18123)
            priority_channels = ACCELERO_CHANNELS
            roster = ACCELEROGRAPH_STATIONS

        server = f'{host}:{port}'
        self.stdout.write(f'[{stype}] Connecting to {server} ...')

        try:
            result = subprocess.run(
                ['slinktool', '-Q', server],
                capture_output=True, text=True, timeout=90,
            )
            output = result.stdout
        except subprocess.TimeoutExpired:
            self.stderr.write(f'ERROR: slinktool timeout ({server})')
            return
        except Exception as e:
            self.stderr.write(f'ERROR: {e}')
            return

        if not output.strip():
            self.stderr.write(f'No output from slinktool ({server})')
            return

        parsed = _parse_q(output, priority_channels)
        self.stdout.write(f'Parsed {len(parsed)} unique stations from ring buffer')

        stations_qs = Station.objects.filter(is_active=True, code__in=roster)

        updated = skipped = 0
        for (net, sta_code), info in parsed.items():
            try:
                station = stations_qs.get(network=net, code=sta_code)
            except Station.DoesNotExist:
                skipped += 1
                continue

            status = StationStatus.compute_status(info['latency'])
            obj, _ = StationStatus.objects.get_or_create(station=station)
            obj.status = status
            obj.latency = info['latency']
            obj.last_packet_time = info['last_packet']
            obj.channel_info = info['channel']
            obj.save()
            StationAvailabilitySample.objects.create(
                station=station,
                sampled_at=datetime.now(timezone.utc),
                status=status,
            )
            updated += 1

        # Stations absent from ring buffer → mark OFF
        now = datetime.now(timezone.utc)
        for sta in stations_qs:
            if (sta.network, sta.code) not in parsed:
                obj, _ = StationStatus.objects.get_or_create(station=sta)
                obj.status = 'off'
                obj.latency = None
                obj.save()
                StationAvailabilitySample.objects.create(
                    station=sta,
                    sampled_at=now,
                    status='off',
                )

        self.stdout.write(self.style.SUCCESS(
            f'[{stype}] Done. Updated: {updated}, not in DB (skipped): {skipped}'
        ))
