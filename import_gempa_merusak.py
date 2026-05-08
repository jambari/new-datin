"""
import_gempa_merusak.py — Parse gempa bumi merusak Papua Excel and upsert into DB.

Run from project root:
    source venv/bin/activate && python import_gempa_merusak.py
"""
import os
import sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "datin_project.settings")
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

import re
import datetime
import openpyxl
from repository.models import GempaMemusak

XLSX = "/mnt/d/data/gempa bumi merusak Papua 1821-2025.xlsx"

# ── Province mapping ──────────────────────────────────────────────────────────
# Kabupaten/Kota → current province after 2022 splits
WILAYAH_PROVINCE = {
    # Papua (eastern, capital Jayapura)
    "Jayapura": "Papua",
    "Biak Numfor": "Papua",
    "Biak": "Papua",
    "Kepulauan Yapen": "Papua",
    "Kep. Yapen": "Papua",
    "Waropen": "Papua",
    "Sarmi": "Papua",
    "Mamberamo": "Papua",
    "Mamberamo Raya": "Papua",
    "Keerom": "Papua",
    "Supiori": "Papua",
    # Papua Pegunungan
    "Tolikara": "Papua Pegunungan",
    "Jayawijaya": "Papua Pegunungan",
    "Wamena": "Papua Pegunungan",
    "Lanny Jaya": "Papua Pegunungan",
    "Puncak Jaya": "Papua Pegunungan",
    "Pegunungan Bintang": "Papua Pegunungan",
    "Yahukimo": "Papua Pegunungan",
    "Nduga": "Papua Pegunungan",
    "Yalimo": "Papua Pegunungan",
    "Mamberamo Tengah": "Papua Pegunungan",
    # Papua Tengah
    "Nabire": "Papua Tengah",
    "Mimika": "Papua Tengah",
    "Paniai": "Papua Tengah",
    "Puncak": "Papua Tengah",
    "Dogiyai": "Papua Tengah",
    "Intan Jaya": "Papua Tengah",
    "Deiyai": "Papua Tengah",
    # Papua Selatan
    "Merauke": "Papua Selatan",
    "Boven Digoel": "Papua Selatan",
    "Bovendigoel": "Papua Selatan",
    "Mappi": "Papua Selatan",
    "Asmat": "Papua Selatan",
    # Papua Barat
    "Manokwari": "Papua Barat",
    "Kaimana": "Papua Barat",
    "Fakfak": "Papua Barat",
    "Teluk Bintuni": "Papua Barat",
    "Teluk Wondama": "Papua Barat",
    "Pegunungan Arfak": "Papua Barat",
    "Manokwari Selatan": "Papua Barat",
    "Sorong Selatan": "Papua Barat",
    # Papua Barat Daya
    "Sorong": "Papua Barat Daya",
    "Raja Ampat": "Papua Barat Daya",
    "Tambrauw": "Papua Barat Daya",
    "Maybrat": "Papua Barat Daya",
    # Old / cross-border names → default to Papua
    "Irian Jaya": "Papua",
    "Badiang": "Papua",   # PNG border, affects eastern Papua
    "Leitre": "Papua",    # PNG territory, affects Papua
}

VALID_PROVINCES = {c[0] for c in GempaMemusak.PROVINCE_CHOICES}

ID_MONTHS = {
    "januari": 1,  "jan": 1,
    "februari": 2, "feb": 2,
    "maret": 3,    "mar": 3,
    "april": 4,    "apr": 4,
    "mei": 5,
    "juni": 6,     "jun": 6,
    "juli": 7,     "jul": 7,
    "agustus": 8,  "agst": 8, "ags": 8, "agus": 8,
    "september": 9,"sept": 9, "sep": 9,
    "oktober": 10, "okt": 10,
    "november": 11,"nov": 11,
    "desember": 12,"des": 12,
}


def parse_date(text):
    if not text:
        return None
    text = re.sub(r'\s+', ' ', str(text).strip().split('\n')[0])
    parts = text.split()
    if len(parts) < 3:
        return None
    try:
        day = int(parts[0])
        month = ID_MONTHS.get(parts[1].lower())
        year = int(parts[2])
        if month:
            return datetime.date(year, month, day)
    except (ValueError, IndexError):
        pass
    return None


def parse_float(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if s in ('-', '', '-'):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_time(val):
    if val is None:
        return None
    if isinstance(val, datetime.time):
        return val
    s = str(val).strip()
    if s in ('-', '', 'WIB'):
        return None
    try:
        parts = s.split(':')
        if len(parts) == 3:
            return datetime.time(int(parts[0]), int(parts[1]), int(float(parts[2])))
        if len(parts) == 2:
            return datetime.time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        pass
    return None


def infer_province(wilayah_raw):
    """Return best matching current province for a wilayah/district name."""
    if not wilayah_raw:
        return "Papua"
    name = str(wilayah_raw).strip()
    # Exact match first
    if name in WILAYAH_PROVINCE:
        return WILAYAH_PROVINCE[name]
    # Partial / case-insensitive
    name_lower = name.lower()
    for key, prov in WILAYAH_PROVINCE.items():
        if key.lower() in name_lower or name_lower in key.lower():
            return prov
    # Fallback
    return "Papua"


def join_lines(parts):
    lines = [str(p).strip() for p in parts if p and str(p).strip() not in ('-', 'WIB')]
    return '\n'.join(lines)


# ── Parse Excel ───────────────────────────────────────────────────────────────

wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
ws = wb.active
all_rows = list(ws.iter_rows(values_only=True))

# Group rows into event blocks (new block starts when col[0] is a number)
blocks = []
current = None
for row in all_rows[2:]:   # skip header rows
    no_val = row[0]
    if no_val is not None and isinstance(no_val, (int, float)):
        if current:
            blocks.append(current)
        current = {"no": int(no_val), "rows": [row]}
    elif current is not None:
        current["rows"].append(row)
if current:
    blocks.append(current)

print(f"Parsed {len(blocks)} event blocks from Excel.")

# ── Process each block ────────────────────────────────────────────────────────

created_count = 0
updated_count = 0

for blk in blocks:
    rows = blk["rows"]
    r0 = rows[0]
    r1 = rows[1] if len(rows) > 1 else [None] * 11
    r2 = rows[2] if len(rows) > 2 else [None] * 11

    no          = blk["no"]
    tanggal_txt = str(r0[1]).strip().split('\n')[0] if r0[1] else ''
    tanggal     = parse_date(r0[1])
    origin_time = parse_time(r0[2])
    lat         = parse_float(r0[3])
    lng         = parse_float(r0[4])
    depth       = parse_float(r0[5])
    mag         = parse_float(r0[6])
    lokasi_raw  = str(r0[7]).strip() if r0[7] else ''
    lokasi      = lokasi_raw if lokasi_raw in ('Darat', 'Laut') else ''
    sumber      = str(r0[10]).strip() if r0[10] else ''

    wilayah_name = str(r1[1]).strip() if r1[1] else ''

    # Always infer current province from wilayah name — the Excel uses old
    # province names (pre-2022 split) so we cannot trust the raw value.
    provinsi = infer_province(wilayah_name)

    # Tsunami: look for 'Tsunami' / 'Tidak Tsunami' in col[1] of any row
    tsunami = None
    for row in rows:
        cell = str(row[1]).strip().lower() if row[1] else ''
        if cell == 'tsunami':
            tsunami = True
            break
        if cell == 'tidak tsunami':
            tsunami = False
            break

    # Multi-row text columns
    wilayah_merasakan_parts = []
    korban_parts = []
    for row in rows:
        if row[8] and str(row[8]).strip() not in ('-', ''):
            wilayah_merasakan_parts.append(str(row[8]).strip())
        if row[9] and str(row[9]).strip() not in ('-', ''):
            korban_parts.append(str(row[9]).strip())

    wilayah_merasakan = '\n'.join(wilayah_merasakan_parts)
    korban_kerusakan  = '\n'.join(korban_parts)

    # Upsert
    obj, created = GempaMemusak.objects.update_or_create(
        no=no,
        defaults=dict(
            tanggal_text      = tanggal_txt,
            tanggal           = tanggal,
            wilayah           = wilayah_name,
            provinsi          = provinsi,
            origin_time       = origin_time,
            latitude          = lat,
            longitude         = lng,
            depth_km          = depth,
            magnitude         = mag,
            lokasi            = lokasi,
            tsunami           = tsunami,
            wilayah_merasakan = wilayah_merasakan,
            korban_kerusakan  = korban_kerusakan,
            sumber            = sumber,
        ),
    )
    status = "CREATED" if created else "UPDATED"
    if created:
        created_count += 1
    else:
        updated_count += 1
    print(f"  [{status}] No={no:2d}  {tanggal_txt[:20]:20s}  wilayah={wilayah_name:20s}  provinsi={provinsi}")

print()
print(f"Done.  Created: {created_count}   Updated: {updated_count}")
