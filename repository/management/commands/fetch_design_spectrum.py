"""
Fetch SNI 1726 design response spectra for all accelerograph stations.

For each Station:
  1. POST lat/lon to rsa.ciptakarya.pu.go.id/2021/process.php → {pga, ss, s1, tl}
  2. GET index.php with those params → extract 4 spectrum curves (site class B/C/D/E)
  3. Upsert StationDesignSpectrum

Usage:
    python manage.py fetch_design_spectrum
    python manage.py fetch_design_spectrum --station JAGI       # single station
    python manage.py fetch_design_spectrum --force              # re-fetch existing
    python manage.py fetch_design_spectrum --delay 1.0          # seconds between requests
"""

import re
import json
import time
import logging

import requests
from django.core.management.base import BaseCommand

from repository.models import Station, StationDesignSpectrum

logger = logging.getLogger(__name__)

BASE_URL   = 'https://rsa.ciptakarya.pu.go.id/2021'
PROCESS    = BASE_URL + '/process.php'
INDEX      = BASE_URL + '/index.php'
TIMEOUT    = 20
SESSION    = requests.Session()
SESSION.verify = False  # site has certificate issues
requests.packages.urllib3.disable_warnings()


def _get_hazard_params(lat, lon):
    """POST lat/lon → {pga, ss, s1, tl} or raise."""
    r = SESSION.post(PROCESS,
                     data={'lintang': lat, 'bujur': lon},
                     timeout=TIMEOUT)
    r.raise_for_status()
    d = r.json()
    return {
        'pga': float(d['pga']),
        'ss':  float(d['ss']),
        's1':  float(d['s1']),
        'tl':  float(d['tl']) if d.get('tl') is not None else None,
    }


def _get_spectra(pga, ss, s1, tl):
    """GET index.php → list of 4 spectrum curves [B, C, D, E]."""
    params = {'pga': pga, 'ss': ss, 's1': s1, 'tl': tl if tl is not None else 6, 'kelas': 0, 'range': 6}
    r = SESSION.get(INDEX, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    html = r.text
    matches = re.findall(r'dataPoints:\s*(\[.*?\])', html, re.DOTALL)
    if len(matches) < 4:
        raise ValueError(f"Expected 4 dataPoints arrays, got {len(matches)}")
    return [json.loads(m) for m in matches[:4]]


class Command(BaseCommand):
    help = 'Fetch SNI 1726 design spectra for all stations from rsa.ciptakarya.pu.go.id'

    def add_arguments(self, parser):
        parser.add_argument('--station', help='Process a single station code')
        parser.add_argument('--force',   action='store_true',
                            help='Re-fetch even if record already exists')
        parser.add_argument('--delay',   type=float, default=0.5,
                            help='Seconds to wait between requests (default 0.5)')

    def handle(self, *args, **options):
        qs = Station.objects.all().order_by('code')
        if options['station']:
            qs = qs.filter(code=options['station'])
            if not qs.exists():
                self.stderr.write(f"Station {options['station']} not found.")
                return

        force = options['force']
        delay = options['delay']

        if not force:
            done = set(StationDesignSpectrum.objects.values_list(
                'station__code', flat=True))
            qs = qs.exclude(code__in=done)

        total = qs.count()
        self.stdout.write(f"Processing {total} stations…")

        ok = err = 0
        for i, station in enumerate(qs, 1):
            try:
                hazard = _get_hazard_params(station.latitude, station.longitude)
                spectra = _get_spectra(**hazard)

                StationDesignSpectrum.objects.update_or_create(
                    station=station,
                    defaults={
                        'pga':        hazard['pga'],
                        'ss':         hazard['ss'],
                        's1':         hazard['s1'],
                        'tl':         hazard['tl'],
                        'spectrum_b': spectra[0],
                        'spectrum_c': spectra[1],
                        'spectrum_d': spectra[2],
                        'spectrum_e': spectra[3],
                    }
                )
                ok += 1
                self.stdout.write(
                    f"[{i}/{total}] {station.code} — "
                    f"PGA={hazard['pga']:.4f} Ss={hazard['ss']:.4f} "
                    f"S1={hazard['s1']:.4f} Tl={hazard['tl']}")
            except Exception as exc:
                err += 1
                self.stderr.write(f"[{i}/{total}] {station.code} FAILED: {exc}")

            if delay and i < total:
                time.sleep(delay)

        self.stdout.write(self.style.SUCCESS(
            f"\nDone — {ok} saved, {err} errors."))
