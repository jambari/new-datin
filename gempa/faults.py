"""Sumber gempa terdekat dari model sumber gempa PuSGeN 2024 (petunjuk di halaman template balai).

Data dari shapefile resmi PuSGeN 2024 (scripts/geodata/pusgen_faults_js.py):
  * gempa/static/gjson/indofaults.js       sesar kerak dangkal (layer yang sama dengan peta Leaflet)
  * gempa/data/pusgen2024_megathrust.json  poligon sumber megathrust
"""
import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

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


@lru_cache(maxsize=1)
def _lines():
    props, a, b, owner = [], [], [], []
    for i, f in enumerate(_read_js(FAULTS)["features"]):
        props.append(f["properties"])
        for part in _parts(f["geometry"]):
            a.extend(part[:-1])
            b.extend(part[1:])
            owner.extend([i] * (len(part) - 1))
    return props, np.array(a, float), np.array(b, float), np.array(owner)


@lru_cache(maxsize=1)
def _zones():
    zones = []
    for f in json.loads(MEGATHRUST.read_text())["features"]:
        polys = [f["geometry"]["coordinates"]] if f["geometry"]["type"] == "Polygon" else f["geometry"]["coordinates"]
        zones.append((f["properties"]["nama"], [np.array(p[0], float) for p in polys]))   # cincin luar
    return zones


def _inside(lon, lat, ring):
    x, y = ring[:, 0], ring[:, 1]
    x2, y2 = np.roll(x, -1), np.roll(y, -1)
    cross = (y > lat) != (y2 > lat)
    xs = x + (lat - y) * (x2 - x) / np.where(y2 == y, 1, y2 - y)
    return bool(np.count_nonzero(cross & (lon < xs)) % 2)


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
    props, a, b, owner = _lines()
    k = math.cos(math.radians(lat))
    ax, ay = (a[:, 0] - lon) * k, a[:, 1] - lat
    dx, dy = (b[:, 0] - a[:, 0]) * k, b[:, 1] - a[:, 1]
    seg2 = dx * dx + dy * dy
    t = np.clip(-(ax * dx + ay * dy) / np.where(seg2 == 0, 1, seg2), 0, 1)
    km = np.hypot(ax + t * dx, ay + t * dy) * 111.2
    i = int(np.argmin(km))
    try:
        deep = depth is not None and float(depth) >= INTERMEDIATE_KM
    except (TypeError, ValueError):
        deep = False
    result = {"ada": False, "max_km": MAX_KM, "dalam": deep, "megathrust": zona_megathrust(lat, lon)}
    if km[i] <= MAX_KM:
        p = props[owner[i]]
        result.update(
            ada=True,
            nama=nama_struktur(p["nama"]) if p["nama"] else TIPE[p["tipe"]].capitalize(),
            segmen=p["segmen"] if p.get("segmen") and p["segmen"] != p["nama"] else "",
            tipe=tipe_sesar(p),
            mmax=p.get("mmax"),
            jarak_km=max(1, round(float(km[i]))),
        )
    return result
