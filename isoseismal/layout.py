"""Gambar peta isoseismal (PNG) dari grid MMI ShakeMap, stasiun akselerograf, dan laporan dirasakan.

Gaya mengikuti template QGIS "BMKG_MMI_Template" (warna skala MMI USGS/Worden dkk. 2011, tabel
skala di bawah peta) dan tata letak peta kerapatan petir (lightning/layout.py): kotak judul,
peta utama di atas OSM, panel kanan (logo, arah utara, skala, legenda, MMI per kabupaten,
sumber data, inset Papua).

Pita intensitas mengikuti kolom tabel skala: I, II–III, IV, V, VI, VII, VIII, IX, X+.
"""
import io
import json
import math
from functools import lru_cache
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from django.conf import settings  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyArrow, PathPatch, Rectangle  # noqa: E402
from matplotlib.path import Path as MplPath  # noqa: E402
from PIL import Image  # noqa: E402

from reporting.osm import ATTRIBUTION, StaticMap  # noqa: E402

from .felt import regions  # noqa: E402

LOGO = Path(settings.BASE_DIR) / "repository" / "static" / "repository" / "images" / "logo-bmkg.png"

# Kolom tabel skala (Worden dkk., 2011) — sama dengan MMI.png di template QGIS.
SCALE = [
    # (label, batas bawah, batas atas, warna, guncangan, kerusakan, PGA %g, PGV cm/s)
    ("I", -1.0, 1.5, "#ffffff", "Tidak terasa", "Tidak ada", "<0.05", "<0.02"),
    ("II-III", 1.5, 3.5, "#bfccff", "Lemah", "Tidak ada", "0.3", "0.1"),
    ("IV", 3.5, 4.5, "#a0e6ff", "Ringan", "Tidak ada", "2.8", "1.4"),
    ("V", 4.5, 5.5, "#80ffff", "Sedang", "Sangat ringan", "6.2", "4.7"),
    ("VI", 5.5, 6.5, "#7aff93", "Kuat", "Ringan", "12", "9.6"),
    ("VII", 6.5, 7.5, "#ffff00", "Sangat kuat", "Sedang", "22", "20"),
    ("VIII", 7.5, 8.5, "#ffc800", "Hebat", "Sedang/Berat", "40", "41"),
    ("IX", 8.5, 9.5, "#ff9100", "Keras", "Berat", "75", "86"),
    ("X+", 9.5, 13.0, "#ff0000", "Ekstrem", "Sangat berat", ">139", ">178"),
]
FAULT_COLOR = "#7c2d12"
# Daratan untuk memotong lapisan MMI (laut tidak diwarnai): kabupaten/kota Indonesia (BIG) + Papua Nugini.
_JS_DIR = Path(settings.BASE_DIR) / "repository" / "static" / "repository" / "js"
LAND_SOURCES = (_JS_DIR / "batas_kabupaten_indo.geojson", _JS_DIR / "png.js")
FELT_MIN = 1.5                                         # di bawah ini (MMI I) tidak diwarnai


def band(mmi):
    """Indeks kolom SCALE untuk nilai MMI."""
    for i, row in enumerate(SCALE):
        if mmi < row[2]:
            return i
    return len(SCALE) - 1


def band_color(mmi):
    return SCALE[band(mmi)][3]


# ── Bantu geometri ────────────────────────────────────────────────────────────

def _dms(v, pos, neg):
    d = abs(v)
    deg = int(d)
    minute = int(round((d - deg) * 60))
    if minute == 60:
        deg, minute = deg + 1, 0
    return f"{deg}°{minute:02d}'{pos if v >= 0 else neg}"


def _project_arrays(smap, lat, lon):
    n = 2 ** smap.zoom
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - np.arcsinh(np.tan(np.radians(lat))) / math.pi) / 2.0 * n
    return (x - smap.x0) * 256, (y - smap.y0) * 256


def _rings(geometry):
    polys = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    return [ring for poly in polys for ring in poly]


def _lines(path):
    from gempa.faults import _read_js

    try:
        data = _read_js(path)
    except (OSError, ValueError):
        return []
    out = []
    for f in data.get("features", []):
        g = f.get("geometry") or {}
        parts = [g.get("coordinates", [])] if g.get("type") == "LineString" else g.get("coordinates", [])
        out.extend(p for p in parts if len(p) >= 2)
    return out


def _fault_paths():
    from gempa.faults import _faults_path

    return _lines(_faults_path()), _lines(_faults_path().with_name("subduksi.js"))


def _km(lat1, lon1, lat2, lon2):
    return math.hypot((lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2)), lat2 - lat1) * 111.2


@lru_cache(maxsize=1)
def _land():
    """[(cincin luar lon/lat sebagai array, bbox)] poligon daratan dari LAND_SOURCES."""
    from gempa.faults import _read_js

    out = []
    for path in LAND_SOURCES:
        try:
            data = json.loads(path.read_text()) if path.suffix == ".geojson" else _read_js(path)
        except (OSError, ValueError):
            continue
        for f in data.get("features", []):
            g = f.get("geometry") or {}
            polys = [g.get("coordinates")] if g.get("type") == "Polygon" else g.get("coordinates") or []
            for poly in polys:
                if not poly or len(poly[0]) < 3:
                    continue
                ring = np.asarray(poly[0], dtype=float)[:, :2]
                out.append((ring, (ring[:, 0].min(), ring[:, 1].min(), ring[:, 0].max(), ring[:, 1].max())))
    return out


def _land_clip(smap, extent):
    """Path daratan (koordinat piksel peta) yang memotong kotak peta, atau None bila data tidak ada."""
    lat0, lat1, lon0, lon1 = extent
    verts, codes = [], []
    for ring, bb in _land():
        if bb[2] < lon0 or bb[0] > lon1 or bb[3] < lat0 or bb[1] > lat1:
            continue
        x, y = _project_arrays(smap, ring[:, 1], ring[:, 0])
        verts.extend(zip(x, y))
        codes.extend([MplPath.MOVETO] + [MplPath.LINETO] * (len(ring) - 2) + [MplPath.CLOSEPOLY])
    return MplPath(verts, codes) if verts else None


def choose_extent(lat, lon, magnitude, mmi, bounds, felt, stations, aspect):
    """Kotak peta (lat0, lat1, lon0, lon1) yang memuat episenter, titik dirasakan, stasiun yang
    mencatat guncangan terasa (MMI ≥ II) dalam 200 km, dan daerah perkiraan MMI ≥ IV."""
    lons, lats = [lon], [lat]
    for p in felt:
        if p.get("lat") is not None:
            lats.append(p["lat"])
            lons.append(p["lon"])
    for s in stations:
        if (s.get("mmi") or 0) >= 2 and _km(lat, lon, s["lat"], s["lon"]) <= 200:
            lats.append(s["lat"])
            lons.append(s["lon"])
    if mmi is not None and mmi.size:
        nlat, nlon = mmi.shape
        rows, cols = np.nonzero(mmi >= 3.5)
        if rows.size:
            lon_min, lat_min, lon_max, lat_max = bounds
            dlon = (lon_max - lon_min) / (nlon - 1)
            dlat = (lat_max - lat_min) / (nlat - 1)
            lons += [lon_min + cols.min() * dlon, lon_min + cols.max() * dlon]
            lats += [lat_max - rows.max() * dlat, lat_max - rows.min() * dlat]
    m = magnitude or 0
    min_half = 0.3 if m < 4 else 0.5 if m < 5 else 0.9 if m < 6 else 1.5
    half_y = max((max(lats) - min(lats)) / 2 * 1.2, (max(lons) - min(lons)) / 2 * 1.2 / aspect, min_half)
    half_y = min(half_y, 4.0)
    half_x = half_y * aspect
    cy = (max(lats) + min(lats)) / 2
    cx = (max(lons) + min(lons)) / 2
    # Episenter harus tetap di dalam peta walau batas maksimum memotong.
    cy = min(max(cy, lat - half_y * 0.8), lat + half_y * 0.8)
    cx = min(max(cx, lon - half_x * 0.8), lon + half_x * 0.8)
    return cy - half_y, cy + half_y, cx - half_x, cx + half_x


def _zoom(span_lon, width_px=1700):
    z = int(math.floor(math.log2(width_px * 360.0 / (256.0 * max(span_lon, 0.01)))))
    return max(5, min(12, z))


# ── Gambar ────────────────────────────────────────────────────────────────────

def render_map(obj, mmi=None, bounds=None):
    """PNG peta isoseismal untuk IsoseismalMap `obj` (grid MMI opsional)."""
    with plt.style.context("default"):
        return _render(obj, mmi, bounds)


def _render(obj, mmi, bounds):
    W, H = 13.0, 9.85                                   # inci
    M = 0.35
    MAP_W, MAP_H = 8.9, 6.15
    STRIP_H = 1.35
    TITLE_H = 0.95
    lat0, lat1, lon0, lon1 = choose_extent(obj.latitude, obj.longitude, obj.magnitude, mmi, bounds,
                                           obj.felt, obj.stations, MAP_W / MAP_H)
    smap = StaticMap(lat0, lat1, lon0, lon1, zoom=_zoom(lon1 - lon0))

    fig = plt.figure(figsize=(W, H), dpi=150)
    fig.patch.set_facecolor("white")
    fig.add_artist(Rectangle((0.006, 0.008), 0.988, 0.984, transform=fig.transFigure, fill=False, lw=1.2,
                             ec="#111"))
    mx, my = M / W, (M + STRIP_H + 0.38) / H
    mw, mh = MAP_W / W, MAP_H / H

    # Kotak judul
    tax = fig.add_axes([mx, my + mh + 0.12 / H, mw, TITLE_H / H])
    tax.set_xticks([]), tax.set_yticks([])
    for s in tax.spines.values():
        s.set_linewidth(1.2)
    t = obj.wit_time
    params = (f"M {obj.magnitude:.1f}  ·  Kedalaman {obj.depth:.0f} km  ·  {abs(obj.latitude):.2f} "
              f"{'LU' if obj.latitude >= 0 else 'LS'} – {abs(obj.longitude):.2f} BT")
    if obj.is_scenario:
        tax.text(0.5, 0.70, "PETA ISOSEISMAL SKENARIO GEMPABUMI", ha="center", va="center", fontsize=14,
                 fontweight="bold", color="#b91c1c")
        tax.text(0.5, 0.30, f"{obj.nama_skenario}  ·  {params}", ha="center", va="center", fontsize=10.5)
    else:
        tax.text(0.5, 0.70, "PETA ISOSEISMAL GEMPABUMI " + obj.wilayah_singkat.upper(), ha="center", va="center",
                 fontsize=14, fontweight="bold")
        tax.text(0.5, 0.30, f"{obj.tanggal}  {t:%H:%M:%S} WIT  ·  {params}", ha="center", va="center",
                 fontsize=10.5)

    # Peta utama
    ax = fig.add_axes([mx, my, mw, mh])
    ax.imshow(smap.image, extent=(0, smap.width, smap.height, 0), zorder=0)
    ax.set_aspect("equal")
    ax.add_patch(Rectangle((0, 0), smap.width, smap.height, fc="white", alpha=0.25, ec="none", zorder=1))

    if mmi is not None and bounds is not None and np.nanmax(mmi) >= FELT_MIN:
        lon_min, lat_min, lon_max, lat_max = bounds
        nlat, nlon = mmi.shape
        glon = np.linspace(lon_min, lon_max, nlon)
        glat = np.linspace(lat_max, lat_min, nlat)
        LON, LAT = np.meshgrid(glon, glat)
        X, Y = _project_arrays(smap, LAT, LON)
        levels = [row[1] for row in SCALE[1:]] + [SCALE[-1][2]]
        colors = [row[3] for row in SCALE[1:]]
        filled = ax.contourf(X, Y, mmi, levels=levels, colors=colors, alpha=0.55, zorder=2, antialiased=True)
        lines = ax.contour(X, Y, mmi, levels=levels[:-1], colors="#374151", linewidths=0.7, alpha=0.8, zorder=2.5)
        land = _land_clip(smap, (lat0, lat1, lon0, lon1))
        if land is not None:                           # hanya daratan; laut tidak diwarnai
            clip = PathPatch(land, transform=ax.transData)
            filled.set_clip_path(clip)
            lines.set_clip_path(clip)

    def proj_line(coords):
        arr = np.asarray(coords, dtype=float)
        return _project_arrays(smap, arr[:, 1], arr[:, 0])

    # Batas kabupaten/kota
    for name, geom, bb in regions("kabupaten"):
        if bb[2] < lon0 or bb[0] > lon1 or bb[3] < lat0 or bb[1] > lat1:
            continue
        for ring in _rings(geom):
            x, y = proj_line(ring)
            ax.plot(x, y, color="#6b7280", lw=0.6, zorder=3, solid_joinstyle="round")
        cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
        if lon0 < cx < lon1 and lat0 < cy < lat1:
            px, py = smap.project(cy, cx)
            label = name.title() if not name.startswith("KOTA ") else "Kota " + name[5:].title()
            ax.text(px, py, label, fontsize=6.8, color="#4b5563", ha="center", va="center", style="italic",
                    zorder=3.2, clip_on=True)

    # Sesar & palung (PuSGeN 2024)
    faults, trench = _fault_paths()
    for coords, lw in [(c, 0.9) for c in faults] + [(c, 1.8) for c in trench]:
        arr = np.asarray(coords, dtype=float)
        if arr[:, 0].max() < lon0 or arr[:, 0].min() > lon1 or arr[:, 1].max() < lat0 or arr[:, 1].min() > lat1:
            continue
        x, y = proj_line(coords)
        ax.plot(x, y, color=FAULT_COLOR, lw=lw, alpha=0.85, zorder=3.5)

    labels = []                                        # (x, y, teks, prioritas, gaya)

    # Stasiun akselerograf
    for s in obj.stations:
        if not (lat0 < s["lat"] < lat1 and lon0 < s["lon"] < lon1):
            continue
        x, y = smap.project(s["lat"], s["lon"])
        fc = band_color(s["mmi"]) if s.get("mmi") is not None else "#d1d5db"
        ax.scatter([x], [y], marker="^", s=70, c=[fc], edgecolors="#111", linewidths=0.8, zorder=5)
        labels.append((x, y, s["code"], 1, dict(fontsize=6.5, color="#111827",
                                                bbox=dict(boxstyle="round,pad=.1", fc="white", ec="none", alpha=0.6))))

    # Titik dirasakan
    for f in obj.felt:
        if f.get("lat") is None or not (lat0 < f["lat"] < lat1 and lon0 < f["lon"] < lon1):
            continue
        x, y = smap.project(f["lat"], f["lon"])
        ax.scatter([x], [y], marker="o", s=55, c=[band_color(f["mmi"])], edgecolors="#111", linewidths=0.9,
                   zorder=6)
        labels.append((x, y, f"{f['place']} ({f['mmi_text']})", 2,
                       dict(fontsize=7.6, fontweight="bold", color="#111827",
                            bbox=dict(boxstyle="round,pad=.15", fc="white", ec="#9ca3af", lw=0.4, alpha=0.88))))

    # Episenter
    ex, ey = smap.project(obj.latitude, obj.longitude)
    ax.scatter([ex], [ey], marker="*", s=420, c="#dc2626", edgecolors="#111", linewidths=1.0, zorder=7)

    ax.set_xlim(0, smap.width)
    ax.set_ylim(smap.height, 0)
    step = _tick_step(lon1 - lon0)
    lon_t = np.arange(math.ceil(lon0 / step) * step, lon1, step)
    lat_t = np.arange(math.ceil(lat0 / step) * step, lat1, step)
    cy, cx = (lat0 + lat1) / 2, (lon0 + lon1) / 2
    ax.set_xticks([smap.project(cy, v)[0] for v in lon_t])
    ax.set_xticklabels([_dms(v, "BT", "BB") for v in lon_t], fontsize=7)
    ax.set_yticks([smap.project(v, cx)[1] for v in lat_t])
    ax.set_yticklabels([_dms(v, "LU", "LS") for v in lat_t], fontsize=7, rotation=90, va="center")
    ax.tick_params(top=True, right=True, labeltop=False, labelright=False, length=3)
    ax.grid(color="#6b7280", lw=0.3, ls="--", alpha=0.6)
    ax.text(smap.width - 6, smap.height - 6, f"{ATTRIBUTION}; sesar & palung: PuSGeN 2024",
            ha="right", va="bottom", fontsize=6.5, bbox=dict(fc="white", ec="none", alpha=0.75, pad=1.5), zorder=8)
    for s in ax.spines.values():
        s.set_linewidth(1.2)

    _place_labels(fig, ax, labels, avoid=[(ex, ey)])
    _panel(fig, obj, smap, (lat0, lat1, lon0, lon1), W, H, mx + mw + 0.2 / W, my, mh + (TITLE_H + 0.12) / H,
           MAP_W)
    _scale_strip(fig, mx, M / H, mw, STRIP_H / H, felt=bool(obj.felt), scenario=obj.is_scenario)
    _sumber_box(fig, obj, mx + mw + 0.2 / W, M / H, 0.988 - (mx + mw + 0.2 / W) - 0.008, STRIP_H / H, W)
    if obj.is_scenario:                                 # tanda air: peta hipotetis, bukan kejadian nyata
        fig.text(mx + mw / 2, my + mh / 2, "SKENARIO", fontsize=96, fontweight="bold", color="#dc2626", alpha=0.16,
                 rotation=28, ha="center", va="center", zorder=100)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor="white")
    plt.close(fig)
    return buf.getvalue()


_OFFSETS = [(8, 4), (8, -12), (-8, 4), (-8, -12), (0, 12), (0, -18), (14, 16), (-14, 16), (14, -24),
            (-14, -24), (22, 0), (-22, 0)]


def _place_labels(fig, ax, labels, avoid=()):
    """Letakkan label tanpa saling tumpuk: coba beberapa posisi di sekitar titik; label laporan
    dirasakan didahulukan, kode stasiun dilewati bila tidak ada tempat."""
    renderer = fig.canvas.get_renderer()
    placed = []
    for ax_x, ax_y in avoid:
        cx, cy = ax.transData.transform((ax_x, ax_y))
        placed.append((cx - 12, cy - 12, cx + 12, cy + 12))
    frame = ax.get_window_extent(renderer)
    for x, y, text, prio, style in sorted(labels, key=lambda l: -l[3]):
        best = None
        for dx, dy in _OFFSETS:
            ha = "left" if dx > 0 else "right" if dx < 0 else "center"
            t = ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points", ha=ha, va="bottom",
                            zorder=8 if prio > 1 else 5.5, annotation_clip=True, **style)
            bb = t.get_window_extent(renderer)
            box = (bb.x0, bb.y0, bb.x1, bb.y1)
            inside = bb.x0 >= frame.x0 and bb.x1 <= frame.x1 and bb.y0 >= frame.y0 and bb.y1 <= frame.y1
            overlap = sum(max(0, min(box[2], p[2]) - max(box[0], p[0])) * max(0, min(box[3], p[3]) - max(box[1], p[1]))
                          for p in placed)
            score = overlap + (0 if inside else 1e6)
            if best is None or score < best[0]:
                if best is not None:
                    best[1].remove()
                best = (score, t, box)
            else:
                t.remove()
            if score == 0:
                break
        if best[0] > 0 and prio <= 1:                  # kode stasiun tidak muat: lewati
            best[1].remove()
            continue
        placed.append(best[2])


def _tick_step(span):
    for step in (0.1, 0.25, 0.5, 1.0, 2.0):
        if span / step <= 7:
            return step
    return 2.0


def _sumber_lines(obj, max_chars):
    """Baris 'sumber gempa terdekat' (sama dengan halaman web), dibungkus selebar panel."""
    import textwrap
    from gempa.faults import sumber_terdekat_baris

    out = []
    for line in sumber_terdekat_baris(obj.latitude, obj.longitude, obj.depth):
        wrapped = textwrap.wrap(line, max_chars) or [line]
        out += ["• " + wrapped[0]] + ["  " + w for w in wrapped[1:]]
    return out


def _sumber_box(fig, obj, x0, y0, w, h, W):
    """Kotak 'Sumber gempa terdekat' (PuSGeN 2024) di bawah panel legenda, sejajar tabel skala."""
    lines = _sumber_lines(obj, max_chars=int(w * W * 15))
    if not lines:
        return
    ax = fig.add_axes([x0, y0, w, h])
    ax.set_xlim(0, 1), ax.set_ylim(0, 1), ax.set_xticks([]), ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_linewidth(1.2)
    ax.text(0.04, 0.90, "Sumber Gempa Terdekat", fontsize=8, fontweight="bold", va="top")
    ax.text(0.04, 0.72, "\n".join(lines[:7]), fontsize=6.6, va="top", linespacing=1.4)
    ax.text(0.04, 0.05, "Model sumber gempa PuSGeN 2024; petunjuk, bukan penentuan sumber.", fontsize=5.6,
            va="bottom", style="italic", color="#4b5563")


def _panel(fig, obj, smap, extent, W, H, px0, py0, ph, map_w_in):
    lat0, lat1, lon0, lon1 = extent
    pw = 0.988 - px0 - 0.008
    pax = fig.add_axes([px0, py0, pw, ph])
    pax.set_xlim(0, 1), pax.set_ylim(0, 1), pax.set_xticks([]), pax.set_yticks([])
    for s in pax.spines.values():
        s.set_linewidth(1.2)
    pw_in, ph_in = pw * W, ph * H

    head = 0.27                                        # tambahan tinggi kepala panel (logo di tengah)

    def y(inches_from_top):
        return 1 - (inches_from_top + head) / ph_in

    def y_abs(inches_from_top):
        return 1 - inches_from_top / ph_in

    # Kepala panel: logo dan nama instansi rata tengah
    if LOGO.exists():
        size = 0.52
        lax = fig.add_axes([px0 + (pw - size / W) / 2, py0 + ph - (0.08 + size) / H, size / W, size / H])
        lax.imshow(Image.open(LOGO)), lax.axis("off")
    pax.text(0.5, y_abs(0.74), "BADAN METEOROLOGI, KLIMATOLOGI, DAN GEOFISIKA", ha="center", va="center",
             fontsize=6.8, fontweight="bold")
    pax.text(0.5, y_abs(0.90), "STASIUN GEOFISIKA KELAS I JAYAPURA", ha="center", va="center", fontsize=7.8,
             fontweight="bold")

    # Arah utara + skala
    pax.text(0.13, y(1.02), "U", ha="center", fontsize=10, fontweight="bold")
    pax.add_patch(FancyArrow(0.13, y(1.42), 0, 0.30 / ph_in, width=0.025, head_width=0.08,
                             head_length=0.12 / ph_in, color="#111"))
    km_per_px = ((lon1 - lon0) * 111.32 * math.cos(math.radians((lat0 + lat1) / 2))) / smap.width
    map_px_per_in = smap.width / map_w_in
    nice = [5, 10, 20, 25, 50, 100, 200]
    bar_km = next((k for k in nice if k / km_per_px / map_px_per_in >= pw_in * 0.35), 200)
    bar_frac = bar_km / km_per_px / map_px_per_in / pw_in
    bx = 0.30
    if bx + bar_frac > 0.95:
        bar_frac = 0.95 - bx
    for i in range(4):
        pax.add_patch(Rectangle((bx + bar_frac * i / 4, y(1.30)), bar_frac / 4, 0.07 / ph_in,
                                fc="#111" if i % 2 == 0 else "white", ec="#111", lw=0.7))
    for frac in (0, 0.5, 1):
        pax.text(bx + bar_frac * frac, y(1.12), f"{bar_km * frac:g}", ha="center", fontsize=6.8)
    pax.text(bx + bar_frac, y(1.47), "Kilometer", ha="right", fontsize=6.5)

    # Legenda
    top = 1.75
    pax.text(0.05, y(top), "Legenda", fontsize=9.5, fontweight="bold")
    items = [
        (Line2D([], [], marker="*", ls="", ms=13, mfc="#dc2626", mec="#111"),
         "Pusat gempa skenario" if obj.is_scenario else "Pusat gempa"),
    ]
    if not obj.is_scenario:
        items += [
            (Line2D([], [], marker="^", ls="", ms=8, mfc="#a0e6ff", mec="#111"), "Stasiun akselerograf (warna = MMI)"),
            (Line2D([], [], marker="o", ls="", ms=7.5, mfc="#bfccff", mec="#111"), "Laporan dirasakan (MMI)"),
        ]
    items += [
        (Line2D([], [], color=FAULT_COLOR, lw=0.9), "Sesar aktif"),
        (Line2D([], [], color=FAULT_COLOR, lw=1.8), "Palung subduksi"),
        (Line2D([], [], color="#6b7280", lw=0.6), "Batas kabupaten/kota"),
        (Line2D([], [], color="#374151", lw=0.7), "Garis isoseismal"),
    ]
    for i, (handle, label) in enumerate(items):
        yy = y(top + 0.25 + i * 0.19)
        ax_h = 0.11
        handle.set_transform(pax.transAxes)
        if handle.get_marker() not in (None, "None", ""):
            handle.set_data([ax_h], [yy])
        else:
            handle.set_data([0.05, 0.17], [yy, yy])
        pax.add_line(handle)
        pax.text(0.22, yy, label, fontsize=7.2, va="center")

    # MMI per kabupaten/kota
    top2 = top + 0.25 + len(items) * 0.19 + 0.1
    rows = [w for w in obj.wilayah if w.get("mmi") is not None and w["mmi"] >= FELT_MIN][:6]
    pax.text(0.05, y(top2), "Perkiraan MMI maksimum per wilayah", fontsize=8, fontweight="bold")
    if rows:
        for i, w in enumerate(rows):
            yy = y(top2 + 0.24 + i * 0.18)
            pax.add_patch(Rectangle((0.05, yy - 0.06 / ph_in), 0.09, 0.12 / ph_in, fc=band_color(w["mmi"]),
                                    ec="#6b7280", lw=0.5))
            pax.text(0.095, yy, SCALE[band(w["mmi"])][0], fontsize=6, ha="center", va="center")
            pax.text(0.18, yy, w["name"], fontsize=7.2, va="center")
        top3 = top2 + 0.24 + len(rows) * 0.18
    else:
        pax.text(0.05, y(top2 + 0.24), "–", fontsize=7.2, va="center")
        top3 = top2 + 0.42

    sources = (["Grid MMI: ShakeMap skenario (GMPE) BMKG Jayapura"] if obj.is_scenario
               else ["Grid MMI: ShakeMap BMKG Jayapura", "Stasiun akselerograf BMKG"])
    sources += obj.felt_sources or []
    sources += ["Batas wilayah: BIG", "Sesar & palung: PuSGeN 2024"]
    pax.text(0.05, y(top3 + 0.05), "Sumber Data:\n" + "\n".join(f"• {s}" for s in dict.fromkeys(sources)),
             fontsize=6.4, va="top", linespacing=1.35)

    # Inset Papua
    inset_h = 1.35
    iax = fig.add_axes([px0 + 0.07 / W, py0 + 0.07 / H, pw - 0.14 / W, inset_h / H])
    # Tanah Papua, diperlebar bila kotak peta melewati batasnya (mis. gempa di Papua Nugini).
    ismap = StaticMap(min(-9.3, lat0 - 0.5), max(0.6, lat1 + 0.5), min(130.0, lon0 - 0.5), max(142.0, lon1 + 0.5),
                      zoom=5)
    iax.imshow(ismap.image, extent=(0, ismap.width, ismap.height, 0))
    rx0, ry0 = ismap.project(lat1, lon0)
    rx1, ry1 = ismap.project(lat0, lon1)
    rx0, rx1 = max(rx0, 1), min(rx1, ismap.width - 1)
    ry0, ry1 = max(ry0, 1), min(ry1, ismap.height - 1)
    iax.add_patch(Rectangle((rx0, ry0), max(rx1 - rx0, 3), max(ry1 - ry0, 3), fill=False, ec="#dc2626", lw=1.5))
    ex, ey = ismap.project(obj.latitude, obj.longitude)
    iax.scatter([ex], [ey], marker="*", s=60, c="#dc2626", edgecolors="#111", linewidths=0.5, zorder=3)
    iax.set_xlim(0, ismap.width), iax.set_ylim(ismap.height, 0)
    iax.set_xticks([]), iax.set_yticks([])
    iax.set_aspect("equal")
    iax.set_anchor("C")


def _scale_strip(fig, x0, y0, w, h, felt=True, scenario=False):
    """Tabel skala intensitas (Worden dkk., 2011) seperti MMI.png di template QGIS."""
    ax = fig.add_axes([x0, y0, w, h])
    ax.set_xlim(0, 1), ax.set_ylim(0, 1), ax.axis("off")
    head_w = 0.17
    col_w = (1 - head_w) / len(SCALE)
    rows = [("GUNCANGAN DIRASAKAN", 4), ("KERUSAKAN POTENSIAL", 5), ("PERCEPATAN PUNCAK (%g)", 6),
            ("KECEPATAN PUNCAK (cm/s)", 7), ("INTENSITAS INSTRUMENTAL", 0)]
    top, bottom = 1.0, 0.13
    rh = (top - bottom) / len(rows)
    for r, (title, idx) in enumerate(rows):
        yy = top - (r + 1) * rh
        ax.add_patch(Rectangle((0, yy), head_w, rh, fc="#f3f4f6", ec="#111", lw=0.7))
        ax.text(head_w / 2, yy + rh / 2, title, fontsize=6.3, fontweight="bold", ha="center", va="center")
        for c, row in enumerate(SCALE):
            xx = head_w + c * col_w
            last = idx == 0
            ax.add_patch(Rectangle((xx, yy), col_w, rh, fc=row[3] if last else "white", ec="#111", lw=0.7))
            ax.text(xx + col_w / 2, yy + rh / 2, row[idx], fontsize=8.5 if last else 6.6, ha="center", va="center",
                    fontweight="bold" if last else "normal")
    if scenario:
        note = ("SKENARIO (hipotetis): warna peta = perkiraan intensitas ShakeMap dari model GMPE tanpa data "
                "stasiun; bukan kejadian nyata dan bukan prakiraan.")
    elif felt:
        note = "Warna peta = perkiraan intensitas ShakeMap yang dikoreksi data stasiun dan laporan dirasakan."
    else:
        note = "Laporan intensitas dirasakan belum tersedia; warna peta = perkiraan ShakeMap dan data stasiun."
    ax.text(0, 0.02, "Skala berdasarkan Worden dkk. (2011). " + note, fontsize=6.5, va="bottom", style="italic")
