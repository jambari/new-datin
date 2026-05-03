"""
Fetch real-time station status from SeedLink via slinktool -Q.
Updates StationStatus for every Station in the database.

Cron (add to /etc/crontab on production):
  */10 * * * * cd /var/www/html && venv/bin/python manage.py fetch_slinktool >> /var/log/fetch_slinktool.log 2>&1
"""
import re
import subprocess
from datetime import datetime, timezone

from django.conf import settings
from django.core.management.base import BaseCommand

from stations.models import Station, StationStatus, StationAvailabilitySample

PRIORITY_CHANNELS = ['HNN', 'HNE', 'HNZ', 'HLN', 'HLE', 'HLZ', 'BHN', 'BHE', 'BHZ']
_DT_RE = re.compile(r'\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+')


def _parse_q(output):
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
            # Prefer higher-priority channel
            ep = PRIORITY_CHANNELS.index(existing['channel']) if existing['channel'] in PRIORITY_CHANNELS else 99
            np_ = PRIORITY_CHANNELS.index(cha) if cha in PRIORITY_CHANNELS else 99
            if np_ < ep:
                station_map[key] = {'channel': cha, 'latency': latency, 'last_packet': end_time}

    return station_map


class Command(BaseCommand):
    help = 'Fetch station status from SeedLink via slinktool -Q and update StationStatus'

    def handle(self, *args, **options):
        host = getattr(settings, 'SEEDLINK_HOST', '202.90.199.206')
        port = getattr(settings, 'SEEDLINK_PORT', 18123)
        server = f'{host}:{port}'

        self.stdout.write(f'Connecting to {server} ...')
        try:
            result = subprocess.run(
                ['slinktool', '-Q', server],
                capture_output=True, text=True, timeout=90,
            )
            output = result.stdout
        except subprocess.TimeoutExpired:
            self.stderr.write('ERROR: slinktool timeout')
            return
        except Exception as e:
            self.stderr.write(f'ERROR: {e}')
            return

        if not output.strip():
            self.stderr.write('No output from slinktool')
            return

        parsed = _parse_q(output)
        self.stdout.write(f'Parsed {len(parsed)} unique stations from ring buffer')

        updated = skipped = 0
        for (net, sta_code), info in parsed.items():
            try:
                station = Station.objects.get(network=net, code=sta_code)
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
        for sta in Station.objects.filter(is_active=True):
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
            f'Done. Updated: {updated}, not in DB (skipped): {skipped}'
        ))
