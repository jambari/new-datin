"""
check_gempa_merusak — Daily check for new significant/tsunami earthquakes in Indonesia.

Fetches the last N days from USGS FDSN, then also pulls BMKG gempaterkini.
Events are added to GempaMemusak when they meet ANY of these criteria:
  • tsunami flag from USGS or BMKG, OR
  • magnitude >= auto_mag (default 7.0), OR
  • reported felt intensity >= V MMI (USGS mmi/cdi field, or BMKG Dirasakan field)

Province is inferred from coordinates using bounding boxes.
"""
import datetime
import json
import re
import urllib.request
import urllib.error
import logging

from django.core.management.base import BaseCommand
from repository.models import GempaMemusak

log = logging.getLogger(__name__)

# ── Province bounding boxes (lat_min, lat_max, lon_min, lon_max) ─────────────
# Order matters: more specific boxes first, catch-all last
PROVINCE_BOUNDS = [
    ('Aceh',                      3.0,  6.0,  95.0, 100.0),
    ('Sumatera Utara',             1.0,  4.5,  97.5, 100.5),
    ('Sumatera Barat',            -3.5,  1.5,  98.5, 102.5),
    ('Riau',                      -1.5,  2.5, 100.5, 104.5),
    ('Kepulauan Riau',             0.0,  4.5, 103.0, 109.0),
    ('Jambi',                     -3.0, -0.5, 101.0, 105.0),
    ('Sumatera Selatan',          -5.5, -1.5, 102.0, 107.0),
    ('Bengkulu',                  -5.5, -2.0,  99.0, 103.5),
    ('Lampung',                   -6.0, -3.5, 103.5, 106.5),
    ('Kepulauan Bangka Belitung', -4.0, -1.0, 105.0, 109.0),
    ('DKI Jakarta',               -6.5, -5.9, 106.5, 107.1),
    ('Banten',                    -7.0, -5.5, 105.0, 107.5),
    ('Jawa Barat',                -8.0, -5.5, 106.5, 109.5),
    ('DI Yogyakarta',             -8.5, -7.5, 110.0, 111.0),
    ('Jawa Tengah',               -8.5, -6.5, 108.5, 111.5),
    ('Jawa Timur',                -9.0, -6.5, 110.5, 115.0),
    ('Bali',                      -9.0, -8.0, 114.5, 116.0),
    ('Nusa Tenggara Barat',       -9.5, -7.5, 115.5, 119.5),
    ('Nusa Tenggara Timur',      -11.5, -7.5, 118.5, 126.0),
    ('Kalimantan Barat',          -3.0,  2.5, 107.5, 115.0),
    ('Kalimantan Tengah',         -4.0,  0.0, 110.0, 116.5),
    ('Kalimantan Selatan',        -4.5, -1.0, 114.5, 117.5),
    ('Kalimantan Utara',           2.0,  5.0, 114.5, 119.0),
    ('Kalimantan Timur',          -3.0,  3.5, 114.5, 119.5),
    ('Sulawesi Utara',            -0.5,  4.0, 123.0, 127.5),
    ('Gorontalo',                 -0.5,  1.5, 121.5, 124.0),
    ('Sulawesi Tengah',           -3.5,  1.5, 119.5, 125.5),
    ('Sulawesi Barat',            -4.0, -0.5, 118.5, 121.5),
    ('Sulawesi Tenggara',         -6.5, -2.5, 121.0, 124.5),
    ('Sulawesi Selatan',          -8.0, -1.5, 119.0, 122.0),
    ('Maluku Utara',              -1.0,  3.5, 125.5, 130.0),
    ('Maluku',                    -9.0, -1.0, 125.5, 135.0),
    ('Papua Barat Daya',          -4.0,  0.5, 130.0, 133.5),
    ('Papua Barat',               -5.0, -0.5, 132.5, 137.0),
    ('Papua Pegunungan',          -7.0, -3.0, 137.0, 141.5),
    ('Papua Tengah',              -6.0, -1.0, 133.0, 138.0),
    ('Papua Selatan',            -10.0, -4.0, 137.0, 141.5),
    ('Papua',                     -9.0,  0.0, 136.0, 141.5),
]

VALID_PROVINCES = {c[0] for c in GempaMemusak.PROVINCE_CHOICES}

ID_MONTHS = [
    '', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
    'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember',
]

ROMAN = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5,
         'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10}
# Longest patterns first so regex matches correctly
_ROMAN_RE = re.compile(r'\b(VIII|VII|VI|IV|IX|X{1,3}|V|III|II|I)\b')


def max_mmi(text):
    """Return max MMI integer parsed from a string like 'IV-V Jayapura, III Nabire'."""
    if not text:
        return 0
    vals = [ROMAN.get(m, 0) for m in _ROMAN_RE.findall(text.upper())]
    return max(vals, default=0)


BMKG_URL = "https://data.bmkg.go.id/DataMKG/TEWS/gempaterkini.json"
USGS_URL = (
    "https://earthquake.usgs.gov/fdsnws/event/1/query"
    "?format=geojson"
    "&minlatitude=-12&maxlatitude=8"
    "&minlongitude=95&maxlongitude=142"
    "&orderby=time"
)


def coords_to_province(lat, lng):
    if lat is None or lng is None:
        return ''
    for prov, lat_min, lat_max, lon_min, lon_max in PROVINCE_BOUNDS:
        if lat_min <= lat <= lat_max and lon_min <= lng <= lon_max:
            return prov
    return ''


def dedup_key(tanggal, lat, lng, mag):
    r_lat = round(lat, 2) if lat is not None else None
    r_lng = round(lng, 2) if lng is not None else None
    r_mag = round(mag, 1) if mag is not None else None
    return (tanggal, r_lat, r_lng, r_mag)


def fetch_json(url, timeout=20):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'datin-bmkg/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as exc:
        log.warning("fetch_json(%s) failed: %s", url, exc)
        return None


class Command(BaseCommand):
    help = 'Check USGS/BMKG for new significant/tsunami earthquakes and add to GempaMemusak'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=2,
                            help='Days to look back (default 2)')
        parser.add_argument('--min-mag', type=float, default=6.0,
                            help='Minimum magnitude to consider (default 6.0)')
        parser.add_argument('--min-mag-tsunami', type=float, default=5.5,
                            help='Minimum magnitude when tsunami flag is set (default 5.5)')
        parser.add_argument('--auto-mag', type=float, default=7.0,
                            help='Magnitude at/above which events are added regardless of tsunami flag (default 7.0)')
        parser.add_argument('--min-mmi', type=int, default=5,
                            help='Minimum reported felt intensity (MMI) to trigger inclusion (default 5 = V MMI)')
        parser.add_argument('--dry-run', action='store_true',
                            help='Print candidates without saving')

    def handle(self, *args, **options):
        days          = options['days']
        min_mag       = options['min_mag']
        min_mag_tsun  = options['min_mag_tsunami']
        auto_mag      = options['auto_mag']
        min_mmi_val   = options['min_mmi']
        dry_run       = options['dry_run']

        start_date = datetime.date.today() - datetime.timedelta(days=days)

        # Build existing dedup set
        existing = set()
        for obj in GempaMemusak.objects.values('tanggal', 'latitude', 'longitude', 'magnitude'):
            existing.add(dedup_key(
                obj['tanggal'], obj['latitude'], obj['longitude'], obj['magnitude']
            ))

        next_no = (GempaMemusak.objects.order_by('-no').values_list('no', flat=True).first() or 0) + 1
        candidates = []  # list of dicts to insert

        # ── 1. USGS FDSN ─────────────────────────────────────────────────────
        usgs_url = (
            f"{USGS_URL}"
            f"&starttime={start_date.isoformat()}"
            f"&minmagnitude={min_mag_tsun}"
        )
        data = fetch_json(usgs_url)
        if data:
            for feat in data.get('features', []):
                props = feat['properties']
                coords = feat['geometry']['coordinates']  # [lon, lat, depth]
                mag      = props.get('mag')
                tsunami  = bool(props.get('tsunami', 0))
                lng, lat, depth = float(coords[0]), float(coords[1]), float(coords[2])
                ts_ms    = props.get('time', 0)
                dt_utc   = datetime.datetime.fromtimestamp(ts_ms / 1000, tz=datetime.timezone.utc)
                dt_wib   = dt_utc + datetime.timedelta(hours=7)
                tanggal  = dt_wib.date()

                if mag is None:
                    continue
                # Instrumental / community intensity from USGS
                usgs_mmi = max(
                    props.get('mmi') or 0,
                    props.get('cdi') or 0,
                )
                felt_v = usgs_mmi >= min_mmi_val
                # Include if: M >= auto_mag, OR tsunami with sufficient mag,
                # OR felt intensity reaches V MMI
                if mag < auto_mag and not (tsunami and mag >= min_mag_tsun) and not felt_v:
                    continue

                key = dedup_key(tanggal, lat, lng, mag)
                if key in existing:
                    continue

                province = coords_to_province(lat, lng)
                if not province:
                    continue  # outside Indonesia bounds

                tanggal_text = f"{dt_wib.day} {ID_MONTHS[dt_wib.month]} {dt_wib.year}"
                origin_time  = dt_wib.time().replace(microsecond=0)

                candidates.append({
                    'tanggal_text':      tanggal_text,
                    'tanggal':           tanggal,
                    'origin_time':       origin_time,
                    'wilayah':           '',
                    'provinsi':          province,
                    'latitude':          round(lat, 4),
                    'longitude':         round(lng, 4),
                    'depth_km':          round(depth, 1),
                    'magnitude':         mag,
                    'lokasi':            'Laut' if depth < 70 and lat < 0 else '',
                    'tsunami':           tsunami or None,
                    'wilayah_merasakan': '',
                    'korban_kerusakan':  '[Auto-detected — perlu verifikasi korban/kerusakan]',
                    'sumber':            'USGS',
                    '_key':              key,
                })

        # ── 2. BMKG gempaterkini ─────────────────────────────────────────────
        bmkg_data = fetch_json(BMKG_URL)
        if bmkg_data:
            for evt in bmkg_data.get('Infogempa', {}).get('gempa', []):
                try:
                    mag = float(evt.get('Magnitude', 0))
                except (TypeError, ValueError):
                    continue

                potensi      = str(evt.get('Potensi', '')).lower()
                tsunami      = 'tsunami' in potensi and 'tidak' not in potensi
                dirasakan    = str(evt.get('Dirasakan', ''))
                felt_v       = max_mmi(dirasakan) >= min_mmi_val

                if mag < auto_mag and not (tsunami and mag >= min_mag_tsun) and not felt_v:
                    continue

                try:
                    coords_str = evt.get('Coordinates', '')
                    lat_s, lng_s = coords_str.split(',')
                    lat, lng = float(lat_s.strip()), float(lng_s.strip())
                except Exception:
                    continue

                # Parse date: BMKG format "DD Mmm YYYY"
                date_str = evt.get('Tanggal', '')
                time_str = evt.get('Jam', '')
                try:
                    parts = date_str.strip().split()
                    month_num = ID_MONTHS.index(parts[1]) if len(parts) >= 3 else 0
                    tanggal   = datetime.date(int(parts[2]), month_num, int(parts[0]))
                except Exception:
                    continue

                depth_str = str(evt.get('Kedalaman', '0')).replace(' km', '').strip()
                try:
                    depth = float(depth_str)
                except ValueError:
                    depth = None

                try:
                    t_parts = time_str.replace(' WIB', '').strip().split(':')
                    origin_time = datetime.time(int(t_parts[0]), int(t_parts[1]),
                                                int(float(t_parts[2])) if len(t_parts) > 2 else 0)
                except Exception:
                    origin_time = None

                key = dedup_key(tanggal, lat, lng, mag)
                if key in existing:
                    continue
                # also skip if already in candidates from USGS
                if any(c['_key'] == key for c in candidates):
                    continue

                province = coords_to_province(lat, lng)
                if not province:
                    continue

                tanggal_text = f"{tanggal.day} {ID_MONTHS[tanggal.month]} {tanggal.year}"
                candidates.append({
                    'tanggal_text':      tanggal_text,
                    'tanggal':           tanggal,
                    'origin_time':       origin_time,
                    'wilayah':           '',
                    'provinsi':          province,
                    'latitude':          round(lat, 4),
                    'longitude':         round(lng, 4),
                    'depth_km':          depth,
                    'magnitude':         mag,
                    'lokasi':            'Laut' if (depth or 0) < 70 else '',
                    'tsunami':           tsunami or None,
                    'wilayah_merasakan': evt.get('Dirasakan', ''),
                    'korban_kerusakan':  '[Auto-detected — perlu verifikasi korban/kerusakan]',
                    'sumber':            'BMKG',
                    '_key':              key,
                })

        # ── Save ─────────────────────────────────────────────────────────────
        if not candidates:
            self.stdout.write("No new significant events found.")
            return

        for c in candidates:
            c_display = (
                f"  {c['tanggal_text']:18s}  M{c['magnitude']}  "
                f"{c['provinsi']:20s}  tsunami={c['tsunami']}  src={c['sumber']}"
            )
            if dry_run:
                self.stdout.write(f"[DRY-RUN] {c_display}")
                continue

            c_save = {k: v for k, v in c.items() if k != '_key'}
            GempaMemusak.objects.create(no=next_no, **c_save)
            existing.add(c['_key'])
            next_no += 1
            self.stdout.write(self.style.SUCCESS(f"[ADDED No={next_no-1}] {c_display}"))

        if not dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"\nDone. Added {len(candidates)} new event(s). "
                f"Total records: {GempaMemusak.objects.count()}"
            ))
