"""Sumber gempa terdekat dari model sumber gempa PuSGeN 2024 (petunjuk di halaman template balai).

Data dari shapefile resmi PuSGeN 2024 (scripts/geodata/pusgen_faults_js.py):
  * gempa/static/gjson/indofaults.js       sesar kerak dangkal (layer yang sama dengan peta Leaflet);
                                           bila tidak ada di app, dicari di STATIC_ROOT/gjson/ (server .188)
  * gempa/data/pusgen2024_megathrust.json  poligon sumber megathrust
Python murni (tanpa numpy) supaya bisa dipakai juga di aplikasi gempa .188.
"""
import json
import math
from functools import lru_cache
from pathlib import Path

from django.conf import settings

BASE = Path(__file__).resolve().parent
FAULTS = BASE / "static" / "gjson" / "indofaults.js"
MEGATHRUST = BASE / "data" / "pusgen2024_megathrust.json"
MAX_KM = 150                             # lebih jauh dari ini: tidak ada sesar yang ditampilkan
INTERMEDIATE_KM = 60                     # kedalaman ≥ ini: kemungkinan bukan sesar kerak dangkal
TIPE = {"geser": "sesar geser", "naik": "sesar naik", "turun": "sesar turun"}
# akhiran nama (Inggris) -> pola nama Indonesia, dicek berurutan
SUFFIX = [
    (" Fold Thrust Belt", "Sabuk Lipatan-Anjakan {}"), (" Fold Thrust", "Sabuk Lipatan-Anjakan {}"),
    (" FTB", "Sabuk Lipatan-Anjakan {}"), (" Back-arc Thrust", "Sesar Naik Busur Belakang {}"),
    (" Backarc Thrust", "Sesar Naik Busur Belakang {}"), (" Backthrust", "Sesar Naik Belakang {}"),
    (" Ridge Thrust", "Sesar Naik Punggungan {}"), (" Spreading Ridge", "Punggungan Pemekaran {}"),
    (" Ridge", "Punggungan {}"), (" Thrust", "Sesar Naik {}"), (" Strait Strikeslip Fault", "Sesar Geser Selat {}"),
    (" Strikeslip Fault", "Sesar Geser {}"), (" Strike Slip", "Sesar Geser {}"), (" Strikeslip", "Sesar Geser {}"),
    (" Oceanic Normal Fault", "Sesar Turun Samudra {}"), (" Fault Zone", "Zona Sesar {}"), (" Trough", "Palung {}"),
    (" Detachment", "Sesar Detachment {}"), (" Fault", "Sesar {}"), (" fault", "Sesar {}"),
]
NAMA = {"North Papua Thrust": "Sesar Naik Papua Utara", "Papua Fold Thrust Belt": "Sabuk Lipatan-Anjakan Papua"}
MEGATHRUST_NAMA = {"Western Java": "Jawa Barat", "Eastern Java": "Jawa Timur", "North Arm Sulawesi": "Lengan Utara Sulawesi",
                   "Central Philippine": "Filipina Tengah", "South Philippine": "Filipina Selatan"}


EJAAN = {"Thurst": "Thrust", "Sumatran": "Sumatra", "Philippine": "Filipina", "Java": "Jawa",
         "Makassar Strait": "Selat Makassar"}
ARAH = {"North": "Utara", "South": "Selatan", "East": "Timur", "West": "Barat"}


def _tempat(nama):
    """'North Buru' -> 'Buru Utara' (nama tempat setelah ejaan Indonesia)."""
    first, _, rest = nama.partition(" ")
    return f"{rest} {ARAH[first]}" if first in ARAH and rest else nama


def nama_struktur(struktur):
    """'Sorong Fault' -> 'Sesar Sorong', 'Manokwari Thrust' -> 'Sesar Naik Manokwari', 'Mamberamo' -> 'Sesar Mamberamo'."""
    for salah, benar in EJAAN.items():                   # salah ketik di shapefile resmi + nama Indonesia
        struktur = struktur.replace(salah, benar)
    if struktur in NAMA:
        return NAMA[struktur]
    for suffix, pattern in SUFFIX:
        if struktur.endswith(suffix):
            return pattern.format(_tempat(struktur[:-len(suffix)]))
    for suffix, pattern in SUFFIX:                       # 'Besoa fault EW' -> 'Sesar Besoa EW'
        if f"{suffix} " in struktur:
            head, tail = struktur.split(f"{suffix} ", 1)
            return f"{pattern.format(_tempat(head))} {tail}"
    return f"Sesar {_tempat(struktur)}"


def nama_megathrust(nama):
    """'Megathrust Western Java' -> 'Megathrust Jawa Barat'."""
    rest = nama.removeprefix("Megathrust ").strip()
    return f"Megathrust {MEGATHRUST_NAMA.get(rest, rest)}"


def tipe_sesar(props):
    kode = (props.get("kode") or "").upper()
    if kode.startswith("SS-LL"):
        return "sesar geser mengiri"
    if kode.startswith("SS-RL"):
        return "sesar geser menganan"
    return TIPE[props["tipe"]]


def _read_js(path):
    text = path.read_text()
    return json.loads(text[text.index("[") + 1:text.rindex("]")])


def _parts(geometry):
    return [geometry["coordinates"]] if geometry["type"] in ("LineString", "Polygon") else geometry["coordinates"]


def _faults_path():
    if FAULTS.exists():
        return FAULTS
    return Path(settings.STATIC_ROOT) / "gjson" / "indofaults.js"


@lru_cache(maxsize=1)
def _lines():
    """(properti tiap sesar, daftar ruas (x1, y1, x2, y2, indeks sesar))."""
    props, segs = [], []
    for i, f in enumerate(_read_js(_faults_path())["features"]):
        props.append(f["properties"])
        for part in _parts(f["geometry"]):
            segs.extend((x1, y1, x2, y2, i) for (x1, y1), (x2, y2) in zip(part, part[1:]))
    return props, segs


@lru_cache(maxsize=1)
def _zones():
    zones = []
    for f in json.loads(MEGATHRUST.read_text())["features"]:
        polys = [f["geometry"]["coordinates"]] if f["geometry"]["type"] == "Polygon" else f["geometry"]["coordinates"]
        zones.append((f["properties"]["nama"], [p[0] for p in polys]))   # cincin luar
    return zones


def _inside(lon, lat, ring):
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def zona_megathrust(lat, lon):
    for nama, rings in _zones():
        if any(_inside(lon, lat, r) for r in rings):
            return nama_megathrust(nama)
    return None


def sumber_terdekat(lat, lon, depth=None):
    """Sesar aktif PuSGeN terdekat dari episenter (jarak ke garis sesar) dan zona megathrust bila di dalamnya,
    atau None bila lokasi tidak valid."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    props, segs = _lines()
    k = math.cos(math.radians(lat))
    best, owner = float("inf"), None
    for x1, y1, x2, y2, i in segs:
        ax, ay, dx, dy = (x1 - lon) * k, y1 - lat, (x2 - x1) * k, y2 - y1
        seg2 = dx * dx + dy * dy
        t = 0.0 if seg2 == 0 else min(1.0, max(0.0, -(ax * dx + ay * dy) / seg2))
        d2 = (ax + t * dx) ** 2 + (ay + t * dy) ** 2
        if d2 < best:
            best, owner = d2, i
    km = math.sqrt(best) * 111.2
    try:
        deep = depth is not None and float(depth) >= INTERMEDIATE_KM
    except (TypeError, ValueError):
        deep = False
    result = {"ada": False, "max_km": MAX_KM, "dalam": deep, "megathrust": zona_megathrust(lat, lon)}
    if km <= MAX_KM:
        p = props[owner]
        result.update(
            ada=True,
            nama=nama_struktur(p["nama"]) if p["nama"] else TIPE[p["tipe"]].capitalize(),
            segmen=p["segmen"] if p.get("segmen") and p["segmen"] != p["nama"] else "",
            tipe=tipe_sesar(p),
            mmax=p.get("mmax"),
            jarak_km=max(1, round(km)),
        )
    return result
