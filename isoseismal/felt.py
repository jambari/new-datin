"""Laporan gempa dirasakan untuk peta isoseismal.

Sumber, diurutkan dari yang paling teliti:
  1. Titik intensitas teramati di stationlist ShakeMap (.50, "composite"): sudah berkoordinat.
  2. Teks "Dirasakan" BMKG (repository.FeltEarthquake, feed gempadirasakan.json),
     mis. "III Jayapura, II - III Sentani".
  3. Teks katalog sendiri (gempa.Gempa.terdampak bila terasa=True),
     mis. "Dirasakan di Kabupaten Keerom dan Kota Jayapura III MMI".
Teks dipecah menjadi (tempat, MMI) lalu tempat dicocokkan ke nama kabupaten/kota dan
distrik (kecamatan) di Tanah Papua dari batas wilayah yang sudah ada di repo.
"""
import datetime
import json
import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings

ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
         "XI": 11, "XII": 12}
_R = r"XII|XI|X|IX|VIII|VII|VI|V|IV|III|II|I"
INTENSITY = re.compile(rf"\b({_R})(?:\s*[-–]\s*({_R}))?\b(?:\s*MMI\b)?")
_SPLIT = re.compile(r"[,;/]|\bdan\b|&", re.I)

# Kotak Tanah Papua (dan laut sekitarnya) untuk menyaring gazetir.
PAPUA_BOX = (129.0, -9.6, 141.1, 1.6)            # lon_min, lat_min, lon_max, lat_max

# Nama kota/tempat yang bukan nama distrik → nama distrik/kabupaten di batas wilayah.
ALIASES = {
    "timika": "MIMIKA BARU", "serui": "YAPEN SELATAN", "genyem": "NIMBORAN", "jayapura": "KOTA JAYAPURA",
    "kota jayapura": "KOTA JAYAPURA", "kabupaten jayapura": "JAYAPURA", "kab jayapura": "JAYAPURA",
    "kab. jayapura": "JAYAPURA", "biak": "BIAK KOTA", "manokwari": "MANOKWARI BARAT", "sorong": "KOTA SORONG",
    "nabire": "NABIRE", "merauke": "MERAUKE", "wamena": "WAMENA", "sentani": "SENTANI", "abepura": "ABEPURA",
    "kotaraja": "ABEPURA", "holtekamp": "MUARA TAMI", "skow": "MUARA TAMI", "koya": "MUARA TAMI",
    "waena": "HERAM", "entrop": "JAYAPURA SELATAN", "hamadi": "JAYAPURA SELATAN", "arso": "ARSO",
    "senggi": "SENGGI", "sarmi": "SARMI", "depapre": "DEPAPRE", "oksibil": "OKSIBIL", "dekai": "DEKAI",
    "enarotali": "PANIAI TIMUR", "ilaga": "ILAGA", "mulia": "MULIA", "tiom": "TIOM", "karubaga": "KARUBAGA",
    "kenyam": "KENYAM", "agats": "AGATS", "kepi": "OBAA", "tanah merah": "MANDOBO", "fakfak": "FAKFAK",
    "kaimana": "KAIMANA", "wasior": "WASIOR", "bintuni": "BINTUNI", "kasonaweja": "MAMBERAMO TENGAH",
}
_BOUNDARY_DIR = Path(settings.BASE_DIR) / "repository" / "static" / "repository" / "js"


def roman(value):
    """Angka romawi MMI dari nilai (dibulatkan), mis. 3.4 → 'III'."""
    if value is None:
        return ""
    n = max(1, min(12, int(round(value))))
    return next(k for k, v in ROMAN.items() if v == n)


def _bbox(coords):
    xs, ys = [], []

    def walk(c):
        if c and isinstance(c[0], (int, float)):
            xs.append(c[0])
            ys.append(c[1])
        else:
            for x in c:
                walk(x)
    walk(coords)
    return min(xs), min(ys), max(xs), max(ys)


def _in_papua(bb):
    return bb[0] >= PAPUA_BOX[0] and bb[2] <= PAPUA_BOX[2] and bb[1] >= PAPUA_BOX[1] and bb[3] <= PAPUA_BOX[3]


@lru_cache(maxsize=2)
def regions(level):
    """[(NAMA, geometri GeoJSON, bbox)] kabupaten/kota ('kabupaten') atau distrik ('kecamatan') di Papua."""
    key = {"kabupaten": "KAB_KOTA", "kecamatan": "KECAMATAN"}[level]
    data = json.loads((_BOUNDARY_DIR / f"batas_{level}_indo.geojson").read_text())
    out = []
    for f in data["features"]:
        name = (f["properties"].get(key) or "").strip()
        if not name or not f.get("geometry"):
            continue
        bb = _bbox(f["geometry"]["coordinates"])
        if _in_papua(bb):
            out.append((name, f["geometry"], bb))
    return out


@lru_cache(maxsize=1)
def gazetteer():
    """{nama huruf kecil: (nama resmi, tingkat, lon, lat)}; titik = titik di dalam poligon."""
    from django.contrib.gis.geos import GEOSGeometry

    gaz = {}
    for level in ("kecamatan", "kabupaten"):              # kabupaten menimpa distrik bernama sama
        for name, geom, _bb in regions(level):
            p = GEOSGeometry(json.dumps(geom)).point_on_surface
            label = name.title() if level == "kecamatan" else _kab_label(name)
            gaz[name.lower()] = (label, level, round(p.x, 4), round(p.y, 4))
    official = dict(gaz)
    for alias, target in ALIASES.items():                # alias menimpa: "Jayapura" = Kota Jayapura
        hit = official.get(target.lower())
        if hit:
            # Nama kota ditulis apa adanya ("Waena", "Timika"); posisi dari distrik/kabupatennya.
            label = hit[0] if hit[1] == "kabupaten" or alias == target.lower() else alias.title()
            gaz[alias] = (label,) + hit[1:]
    return gaz


def _kab_label(name):
    return f"Kota {name[5:].title()}" if name.startswith("KOTA ") else f"Kab. {name.title()}"


_DROP = re.compile(r"\b(dirasakan|dirasakannya|oleh|masyarakat|warga|di|wilayah|daerah|dengan|skala|"
                   r"intensitas|mmi|kabupaten|kab|distrik|kecamatan|sekitar|getaran|lemah|kuat|"
                   r"dan|selama|detik|beberapa|sebagian|seluruh|tidak|ada|laporan)\b\.?", re.I)


def _match_places(chunk):
    """Tempat-tempat yang dikenali dalam satu potongan teks: [(label, lon, lat)] atau [(teks, None, None)]."""
    text = " " + re.sub(r"\s+", " ", chunk.lower()) + " "
    gaz = gazetteer()
    found, taken = [], []
    for name in sorted(gaz, key=len, reverse=True):
        for m in re.finditer(rf"(?<![a-z]){re.escape(name)}(?![a-z])", text):
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue
            label, _lvl, lon, lat = gaz[name]
            taken.append((m.start(), m.end()))
            found.append((m.start(), label, lon, lat))
    if found:
        return [(label, lon, lat) for _s, label, lon, lat in sorted(found)]
    rest = _DROP.sub(" ", chunk)
    rest = re.sub(r"\d+\s*km\b|\b(utara|selatan|timur|barat|laut|daya)\w*", " ", rest, flags=re.I)
    rest = re.sub(r"[^\w\s.-]", " ", rest)
    rest = re.sub(r"\s+", " ", rest).strip(" .-")
    return [(rest.title(), None, None)] if len(rest) >= 3 else []


def parse_felt_text(text):
    """[{place, mmi, mmi_text, lat, lon}] dari teks dirasakan.

    Dua gaya penulisan: BMKG ("III Jayapura, II-III Sentani": skala di depan tempat) dan
    narasi katalog ("Dirasakan di Keerom dan Kota Jayapura III MMI": skala di belakang).
    """
    if not text:
        return []
    tokens = []                                           # ("mmi", lo, hi, teks) | ("place", potongan)
    pos = 0
    for m in INTENSITY.finditer(text):
        tokens += [("place", c) for c in _SPLIT.split(text[pos:m.start()]) if c.strip()]
        lo = ROMAN[m.group(1)]
        hi = ROMAN[m.group(2)] if m.group(2) else lo
        tokens.append(("mmi", min(lo, hi), max(lo, hi), m.group(0).replace(" MMI", "").replace("MMI", "").strip()))
        pos = m.end()
    tokens += [("place", c) for c in _SPLIT.split(text[pos:]) if c.strip()]
    if not any(t[0] == "mmi" for t in tokens):
        return []
    prefix = tokens[0][0] == "mmi"
    out, pending, current = [], [], None

    def emit(chunks, level):
        for c in chunks:
            for label, lon, lat in _match_places(c):
                out.append({"place": label, "mmi": (level[1] + level[2]) / 2, "mmi_text": _norm(level[3]),
                            "lat": lat, "lon": lon})

    for t in tokens:
        if t[0] == "mmi":
            if prefix:
                current = t
            else:
                emit(pending, t)
                pending = []
                current = t
        elif prefix:
            emit([t[1]], current)
        else:
            pending.append(t[1])
    if pending and current is not None and not prefix:
        emit(pending, current)                            # sisa tempat setelah skala terakhir
    return merge(out)


def _norm(text):
    return re.sub(r"\s*[-–]\s*", "-", text).strip()


def merge(items):
    """Satu baris per tempat (nama sama), ambil MMI tertinggi; urut MMI menurun."""
    best = {}
    for it in items:
        key = it["place"].lower()
        if key not in best or it["mmi"] > best[key]["mmi"]:
            best[key] = dict(it)
        elif best[key].get("lat") is None and it.get("lat") is not None:
            best[key].update(lat=it["lat"], lon=it["lon"])
    return sorted(best.values(), key=lambda r: (-r["mmi"], r["place"]))


# ── Pencarian laporan untuk satu kejadian ────────────────────────────────────

MATCH_SECONDS = 90
MATCH_DEG = 1.0


WIT_OFFSET = datetime.timedelta(hours=9)


def gempa_time(tanggal, origin):
    """Waktu UTC baris katalog Gempa. origin biasanya 'HH:MM:SS' UTC; baris lama 'HH:MM:SS WIT' (tanggal WIT)."""
    text = str(origin or "").strip()
    try:
        t = datetime.datetime.strptime(f"{tanggal} {text[:8]}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    if "WIT" in text.upper():
        t -= WIT_OFFSET
    return t.replace(tzinfo=datetime.timezone.utc)


def gempa_lat(value):
    """Lintang katalog: '-2.84' atau '2.74° LS' / '0.5° LU'."""
    text = str(value or "").strip().upper()
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    if not m:
        return None
    v = float(m.group(0))
    return -abs(v) if "LS" in text else abs(v) if "LU" in text else v


def felt_events(since, until=None):
    """[(waktu UTC, lintang, bujur)] gempa dirasakan: BMKG gempabumi-dirasakan + katalog terasa=True."""
    from gempa.models import Gempa
    from repository.models import FeltEarthquake

    until = until or datetime.datetime.now(datetime.timezone.utc)
    out = [(f.event_datetime, f.latitude, f.longitude)
           for f in FeltEarthquake.objects.filter(event_datetime__range=(since, until))]
    rows = Gempa.objects.filter(terasa=True, tanggal__gte=(since - WIT_OFFSET).date(),
                                tanggal__lte=(until + WIT_OFFSET).date()).values("tanggal", "origin", "lintang", "bujur")
    for row in rows:
        t, lat = gempa_time(row["tanggal"], row["origin"]), gempa_lat(row["lintang"])
        if t is None or lat is None or row["bujur"] is None or not since <= t <= until:
            continue
        lon = float(row["bujur"])
        # Kejadian yang sama di BMKG dan katalog cukup sekali.
        if not any(abs((t - o[0]).total_seconds()) <= MATCH_SECONDS and abs(lat - o[1]) <= MATCH_DEG for o in out):
            out.append((t, lat, lon))
    return sorted(out)


def felt_reports(event_time, lat, lon):
    """[(sumber, teks)] laporan dirasakan untuk kejadian pada event_time (UTC) di (lat, lon)."""
    from gempa.models import Gempa
    from repository.models import FeltEarthquake

    reports = []
    win = datetime.timedelta(seconds=MATCH_SECONDS)
    for f in FeltEarthquake.objects.filter(event_datetime__range=(event_time - win, event_time + win)):
        if abs(f.latitude - lat) <= MATCH_DEG and abs(f.longitude - lon) <= MATCH_DEG and f.dirasakan:
            reports.append(("BMKG (gempabumi dirasakan)", f.dirasakan))
    days = {event_time.date(), (event_time - win).date(), (event_time + win).date()}
    days |= {(event_time + datetime.timedelta(hours=9)).date()}            # baris lama bertanggal WIT
    rows = Gempa.objects.filter(tanggal__in=days, terasa=True).values("tanggal", "origin", "terdampak", "narasi")
    for row in rows:
        t = gempa_time(row["tanggal"], row["origin"])
        if t is None or abs((t - event_time).total_seconds()) > MATCH_SECONDS:
            continue
        for field in ("terdampak", "narasi"):
            text = row.get(field) or ""
            if INTENSITY.search(text):
                reports.append(("Katalog Stasiun Geofisika Jayapura", text))
                break
    return reports


def collect_felt(event_time, lat, lon, observed=()):
    """(titik dirasakan gabungan, teks sumber, daftar sumber)."""
    items, texts, sources = [], [], []
    for o in observed:
        items.append({"place": o["place"], "mmi": o["mmi"], "mmi_text": roman(o["mmi"]),
                      "lat": o["lat"], "lon": o["lon"]})
    if observed:
        sources.append("ShakeMap (intensitas teramati)")
    for source, text in felt_reports(event_time, lat, lon):
        parsed = parse_felt_text(text)
        if parsed:
            items += parsed
            texts.append(text.strip())
            if source not in sources:
                sources.append(source)
    return merge(items), "\n".join(dict.fromkeys(texts)), sources
