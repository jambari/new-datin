"""
import_gempa_perwilayah.py — Import additional Papua province earthquake data
from Katalog Gempa Perwilayah 1821-2024 update.xlsx into GempaMemusak.

Processes sheets: Papua Barat, Papua Tengah, Papua Pegunungan
(Papua Barat Daya and Papua Selatan are currently empty in the file;
 Papua sheet is already imported via import_gempa_merusak.py)

Run from project root:
    source venv/bin/activate && python import_gempa_perwilayah.py
"""
import os, sys, django, datetime, re
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "datin_project.settings")
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

import openpyxl
from repository.models import GempaMemusak

XLSX = "/mnt/d/data/Katalog Gempa Perwilayah 1821- 2024 update.xlsx"

# Sheets to import and their canonical current province name
TARGET_SHEETS = {
    "Papua Barat":      "Papua Barat",
    "Papua Tengah":     "Papua Tengah",
    "Papua Pegunungan": "Papua Pegunungan",
}

# District → current province overrides (post-2022 splits)
# These districts were in Papua Barat (old) but now belong to Papua Barat Daya
DISTRICT_PROVINCE_OVERRIDE = {
    "Sorong":          "Papua Barat Daya",
    "Sorong Selatan":  "Papua Barat",    # still Papua Barat
    "Raja Ampat":      "Papua Barat Daya",
    "Tambrauw":        "Papua Barat Daya",
    "Maybrat":         "Papua Barat Daya",
    # Districts firmly in Papua Barat
    "Manokwari":           "Papua Barat",
    "Manokwari Selatan":   "Papua Barat",
    "Kaimana":             "Papua Barat",
    "Fakfak":              "Papua Barat",
    "Teluk Bintuni":       "Papua Barat",
    "Teluk Wondama":       "Papua Barat",
    "Pegunungan Arfak":    "Papua Barat",
    # Papua Tengah
    "Nabire":   "Papua Tengah",
    "Mimika":   "Papua Tengah",
    "Paniai":   "Papua Tengah",
    "Deiyai":   "Papua Tengah",
    "Dogiyai":  "Papua Tengah",
    "Intan Jaya": "Papua Tengah",
    # Papua Pegunungan
    "Yahukimo":          "Papua Pegunungan",
    "Tolikara":          "Papua Pegunungan",
    "Jayawijaya":        "Papua Pegunungan",
    "Lanny Jaya":        "Papua Pegunungan",
    "Puncak Jaya":       "Papua Pegunungan",
    "Pegunungan Bintang": "Papua Pegunungan",
    "Nduga":             "Papua Pegunungan",
    "Mamberamo Tengah":  "Papua Pegunungan",
    "Yalimo":            "Papua Pegunungan",
}

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


def parse_date(val):
    if val is None:
        return None, ''
    if isinstance(val, (datetime.datetime,)):
        return val.date(), val.strftime("%-d %B %Y")
    if isinstance(val, datetime.date):
        return val, val.strftime("%-d %B %Y")
    text = re.sub(r'\s+', ' ', str(val).strip().split('\n')[0])
    parts = text.split()
    if len(parts) >= 3:
        try:
            day = int(parts[0])
            month = ID_MONTHS.get(parts[1].lower())
            year = int(parts[2])
            if month:
                return datetime.date(year, month, day), text
        except (ValueError, IndexError):
            pass
    return None, text


def parse_float(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if s in ('-', '', 'WIB'):
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
    if isinstance(val, datetime.datetime):
        return val.time()
    s = str(val).strip()
    if s in ('-', '', 'WIB'):
        return None
    try:
        parts = s.split(':')
        if len(parts) >= 2:
            return datetime.time(int(parts[0]), int(parts[1]),
                                 int(float(parts[2])) if len(parts) > 2 else 0)
    except (ValueError, IndexError):
        pass
    return None


def infer_province(wilayah_raw, sheet_province):
    """Look up current province; fall back to sheet_province if unknown."""
    if not wilayah_raw:
        return sheet_province
    # Strip "Kab." / "Kota" prefixes
    name = re.sub(r'^(Kab\.|Kota|Kabupaten)\s+', '', str(wilayah_raw).strip(), flags=re.I)
    # Exact match
    if name in DISTRICT_PROVINCE_OVERRIDE:
        return DISTRICT_PROVINCE_OVERRIDE[name]
    # Partial match
    name_lower = name.lower()
    for key, prov in DISTRICT_PROVINCE_OVERRIDE.items():
        if key.lower() in name_lower:
            return prov
    # Fall back to the sheet's province
    return sheet_province


def parse_sheet(ws, sheet_province):
    """Parse one sheet into a list of event dicts."""
    all_rows = list(ws.iter_rows(values_only=True))
    # Find the data start (row after the 'Lat / Long' sub-header row at index 6)
    data_rows = [r for r in all_rows[7:] if any(c is not None for c in r)]

    blocks = []
    current = None
    for row in data_rows:
        if len(row) < 2:
            continue
        val = row[1]
        if val is not None and isinstance(val, (int, float)) and float(val) == int(float(val)):
            if current:
                blocks.append(current)
            current = {"sheet_no": int(val), "rows": [row]}
        elif current is not None:
            current["rows"].append(row)
    if current:
        blocks.append(current)

    events = []
    for blk in blocks:
        rows = blk["rows"]
        r0 = rows[0]
        r1 = rows[1] if len(rows) > 1 else [None] * 12
        # col offsets: 1=No, 2=Tanggal/Wilayah, 3=OT, 4=Lat, 5=Long, 6=Depth, 7=Mag, 8=Lokasi, 9=WilMerasakan, 10=Korban, 11=Sumber
        tanggal, tanggal_txt = parse_date(r0[2])
        wilayah_name = str(r1[2]).strip() if len(r1) > 2 and r1[2] else ''
        provinsi = infer_province(wilayah_name, sheet_province)

        lokasi_raw = str(r0[8]).strip() if len(r0) > 8 and r0[8] else ''
        lokasi = lokasi_raw if lokasi_raw in ('Darat', 'Laut') else ''

        # Tsunami marker in col[2] of any row
        tsunami = None
        for row in rows:
            cell = str(row[2]).strip().lower() if len(row) > 2 and row[2] else ''
            if cell == 'tsunami':
                tsunami = True
                break
            if cell == 'tidak tsunami':
                tsunami = False
                break

        wil_parts   = [str(r[9]).strip()  for r in rows if len(r) > 9  and r[9]  and str(r[9]).strip()  not in ('-', '')]
        korb_parts  = [str(r[10]).strip() for r in rows if len(r) > 10 and r[10] and str(r[10]).strip() not in ('-', '')]

        events.append({
            "tanggal_text":      tanggal_txt,
            "tanggal":           tanggal,
            "wilayah":           wilayah_name,
            "provinsi":          provinsi,
            "origin_time":       parse_time(r0[3]) if len(r0) > 3 else None,
            "latitude":          parse_float(r0[4]) if len(r0) > 4 else None,
            "longitude":         parse_float(r0[5]) if len(r0) > 5 else None,
            "depth_km":          parse_float(r0[6]) if len(r0) > 6 else None,
            "magnitude":         parse_float(r0[7]) if len(r0) > 7 else None,
            "lokasi":            lokasi,
            "tsunami":           tsunami,
            "wilayah_merasakan": '\n'.join(wil_parts),
            "korban_kerusakan":  '\n'.join(korb_parts),
            "sumber":            str(r0[11]).strip() if len(r0) > 11 and r0[11] else '',
        })
    return events


# ── Deduplication key ─────────────────────────────────────────────────────────
def dedup_key(evt):
    """Tuple used to detect if an event is already in the DB."""
    lat = round(evt["latitude"],  2) if evt["latitude"]  else None
    lng = round(evt["longitude"], 2) if evt["longitude"] else None
    mag = round(evt["magnitude"], 1) if evt["magnitude"] else None
    return (evt["tanggal"], lat, lng, mag)


# Build dedup set from existing records
existing_keys = set()
for obj in GempaMemusak.objects.values("tanggal", "latitude", "longitude", "magnitude"):
    lat = round(obj["latitude"],  2) if obj["latitude"]  else None
    lng = round(obj["longitude"], 2) if obj["longitude"] else None
    mag = round(obj["magnitude"], 1) if obj["magnitude"] else None
    existing_keys.add((obj["tanggal"], lat, lng, mag))

# Starting no
next_no = (GempaMemusak.objects.order_by('-no').values_list('no', flat=True).first() or 0) + 1

# ── Main import ───────────────────────────────────────────────────────────────
wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
created_count = 0
skipped_count = 0

for sheet_name, sheet_province in TARGET_SHEETS.items():
    ws = wb[sheet_name]
    events = parse_sheet(ws, sheet_province)
    print(f"\n[{sheet_name}]  {len(events)} events parsed")

    for evt in events:
        key = dedup_key(evt)
        if key in existing_keys:
            print(f"  SKIP (dup)  {evt['tanggal_text'][:20]:20s}  {evt['wilayah']}")
            skipped_count += 1
            continue

        GempaMemusak.objects.create(no=next_no, **evt)
        print(f"  CREATED  No={next_no:3d}  {evt['tanggal_text'][:20]:20s}  {evt['wilayah']:22s}  {evt['provinsi']}")
        existing_keys.add(key)
        next_no += 1
        created_count += 1

print(f"\nDone.  Created: {created_count}   Skipped (duplicates): {skipped_count}")
print(f"Total GempaMemusak records: {GempaMemusak.objects.count()}")
