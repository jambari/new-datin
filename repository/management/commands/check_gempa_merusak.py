"""
check_gempa_merusak — Scrape BMKG "Gempa Bumi Dirasakan" and add VI / VI-VII MMI events.

The public page https://www.bmkg.go.id/gempabumi/gempabumi-dirasakan renders the
JSON feed at https://data.bmkg.go.id/DataMKG/TEWS/gempadirasakan.json.

An event is inserted into the Gempa Merusak catalog ONLY when the "Wilayah (MMI)"
remark (the `Dirasakan` field) mentions VI MMI or VI-VII MMI.
"""
import datetime
import json
import logging
import re
import urllib.error
import urllib.request

from django.core.management.base import BaseCommand

from repository.models import GempaMemusak

log = logging.getLogger(__name__)

BMKG_DIRASAKAN_URL = "https://data.bmkg.go.id/DataMKG/TEWS/gempadirasakan.json"

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

MONTH_NUM = {
    'jan': 1, 'januari': 1,
    'feb': 2, 'februari': 2,
    'mar': 3, 'maret': 3,
    'apr': 4, 'april': 4,
    'mei': 5,
    'jun': 6, 'juni': 6,
    'jul': 7, 'juli': 7,
    'agu': 8, 'ags': 8, 'agst': 8, 'agustus': 8,
    'sep': 9, 'sept': 9, 'september': 9,
    'okt': 10, 'oktober': 10,
    'nov': 11, 'november': 11,
    'des': 12, 'desember': 12,
}

# "Wilayah (MMI)" remark patterns: VI-VII range or standalone VI numeral.
_RANGE_RE = re.compile(r'\b([IVX]+)\s*[-–]\s*([IVX]+)\b')
_SINGLE_RE = re.compile(r'(?<![-–])\b(VI|VII|VIII|IV|IX|III|II|I)\b(?![-–])')


def vi_mentioned(text):
    """Return True if the Wilayah (MMI) remark mentions VI MMI or VI-VII MMI."""
    if not text:
        return False
    t = ' '.join(str(text).split()).upper()
    t = re.sub(r'\s*[-–]\s*', '-', t)
    if re.search(r'\bVI-VII\b', t):
        return True
    singles = _SINGLE_RE.findall(t)
    return 'VI' in singles


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


def parse_tanggal(text):
    """'26 Sep 2026' → datetime.date"""
    if not text:
        return None
    parts = str(text).strip().split()
    if len(parts) < 3:
        return None
    try:
        day = int(parts[0])
        month = MONTH_NUM.get(parts[1].lower())
        year = int(parts[2])
        if month:
            return datetime.date(year, month, day)
    except (ValueError, IndexError):
        pass
    return None


def parse_jam(text):
    """'02:39:29 WIB' → datetime.time"""
    if not text:
        return None
    s = str(text).replace('WIB', '').replace('WITA', '').replace('WIT', '').strip()
    try:
        parts = s.split(':')
        return datetime.time(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return None


def parse_depth(text):
    """'9 km' → float"""
    if not text:
        return None
    try:
        return float(str(text).replace('km', '').strip())
    except ValueError:
        return None


class Command(BaseCommand):
    help = 'Scrape BMKG gempabumi-dirasakan and add VI / VI-VII MMI events to Gempa Merusak'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30,
                            help='Only consider events from the last N days (default 30)')
        parser.add_argument('--dry-run', action='store_true',
                            help='Print candidates without saving')

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']

        data = fetch_json(BMKG_DIRASAKAN_URL)
        if not data:
            self.stderr.write("Failed to fetch gempadirasakan feed.")
            return

        gempa_list = data.get('Infogempa', {}).get('gempa', [])
        self.stdout.write(f"Fetched {len(gempa_list)} felt-earthquake event(s).")

        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)

        existing = set()
        for obj in GempaMemusak.objects.values('tanggal', 'latitude', 'longitude', 'magnitude'):
            existing.add(dedup_key(
                obj['tanggal'], obj['latitude'], obj['longitude'], obj['magnitude']
            ))

        next_no = (GempaMemusak.objects.order_by('-no').values_list('no', flat=True).first() or 0) + 1

        added = 0
        for evt in gempa_list:
            dirasakan = str(evt.get('Dirasakan', '') or '')
            if not vi_mentioned(dirasakan):
                continue

            tanggal = parse_tanggal(evt.get('Tanggal'))
            if not tanggal:
                self.stderr.write(f"  [SKIP] cannot parse date: {evt.get('Tanggal')!r}")
                continue

            # Optional recency filter using the feed's ISO DateTime
            dt_str = evt.get('DateTime', '')
            if dt_str:
                try:
                    dt = datetime.datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                    if dt < cutoff:
                        self.stdout.write(f"  [SKIP] older than {days} days: {evt.get('Tanggal')}")
                        continue
                except ValueError:
                    pass

            coords = str(evt.get('Coordinates', '') or '').split(',')
            try:
                lat = float(coords[0].strip())
                lng = float(coords[1].strip())
            except (IndexError, ValueError):
                self.stderr.write(f"  [SKIP] cannot parse coordinates: {evt.get('Coordinates')!r}")
                continue

            try:
                mag = float(str(evt.get('Magnitude', '') or '').replace(',', '.'))
            except ValueError:
                mag = None

            key = dedup_key(tanggal, lat, lng, mag)
            if key in existing:
                self.stdout.write(f"  [EXISTS] {tanggal} M{mag} {evt.get('Wilayah', '')[:40]}")
                continue

            wilayah = str(evt.get('Wilayah', '') or '')
            lokasi = ''
            w_lower = wilayah.lower()
            if 'laut' in w_lower:
                lokasi = 'Laut'
            elif 'darat' in w_lower:
                lokasi = 'Darat'

            province = coords_to_province(lat, lng)
            if province not in VALID_PROVINCES:
                province = ''

            tanggal_text = f"{tanggal.day} {ID_MONTHS[tanggal.month]} {tanggal.year}"

            record = dict(
                tanggal_text=tanggal_text,
                tanggal=tanggal,
                origin_time=parse_jam(evt.get('Jam')),
                wilayah=wilayah,
                provinsi=province,
                latitude=round(lat, 4),
                longitude=round(lng, 4),
                depth_km=parse_depth(evt.get('Kedalaman')),
                magnitude=mag,
                lokasi=lokasi,
                tsunami=None,
                wilayah_merasakan=dirasakan,
                korban_kerusakan='[Auto dari gempabumi-dirasakan — perlu verifikasi korban/kerusakan]',
                sumber='BMKG Dirasakan',
            )

            display = f"{tanggal_text:20s} M{mag}  {province:20s}  {dirasakan[:50]}"
            if dry_run:
                self.stdout.write(f"[DRY-RUN] {display}")
                continue

            GempaMemusak.objects.create(no=next_no, **record)
            existing.add(key)
            next_no += 1
            added += 1
            self.stdout.write(self.style.SUCCESS(f"[ADDED No={next_no - 1}] {display}"))

        if dry_run:
            self.stdout.write("Dry run — nothing saved.")
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\nDone. Added {added} new VI/VI-VII MMI event(s). "
                f"Total records: {GempaMemusak.objects.count()}"
            ))
