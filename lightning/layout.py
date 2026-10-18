"""Layout peta kerapatan sambaran petir Kota Jayapura (PNG siap tempel ke laporan bulanan).

Tata letak mengikuti template laporan: kotak judul, peta utama persegi yang dipotong ke batas
Kota Jayapura, dan panel kanan (logo BMKG, arah utara, skala, legenda, sumber data, inset peta).
Kelas kerapatan memakai nilai IDW grid bulanan (sama dengan halaman /lightning/grid/), hanya
di sekitar sel yang benar-benar tersambar.
"""
import io
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from django.conf import settings  # noqa: E402
from django.contrib.gis.geos import GEOSGeometry  # noqa: E402
from matplotlib.patches import FancyArrow, PathPatch, Rectangle  # noqa: E402
from matplotlib.path import Path as MplPath  # noqa: E402
from PIL import Image  # noqa: E402
from scipy import ndimage  # noqa: E402

from reporting.osm import ATTRIBUTION, StaticMap  # noqa: E402

BULAN = ["", "JANUARI", "FEBRUARI", "MARET", "APRIL", "MEI", "JUNI", "JULI", "AGUSTUS", "SEPTEMBER",
         "OKTOBER", "NOVEMBER", "DESEMBER"]
BULAN_TITLE = [b.title() for b in BULAN]
BOUNDARY = Path(__file__).resolve().parent / "static" / "lightning" / "kota_jayapura.geojson"
LOGO = Path(settings.BASE_DIR) / "repository" / "static" / "repository" / "images" / "logo-bmkg.png"
CLASSES = [("Rendah (0–5)", "#8fd16f"), ("Sedang (5–10)", "#ffff73"), ("Tinggi (>10)", "#ff7f7f")]
GRID, LAT0, LON0, N = 0.01, -3.01, 140.21, 100


def _features():
    data = json.loads(BOUNDARY.read_text())
    return [(f["properties"]["KECAMATAN"], GEOSGeometry(json.dumps(f["geometry"]))) for f in data["features"]]


def _rings(geom):
    polys = [geom] if geom.geom_type == "Polygon" else list(geom)
    return [ring for poly in polys for ring in poly]


def _path(rings, smap):
    verts, codes = [], []
    for ring in rings:
        pts = [smap.project(lat, lon) for lon, lat in ring.coords]
        verts += pts
        codes += [MplPath.MOVETO] + [MplPath.LINETO] * (len(pts) - 2) + [MplPath.CLOSEPOLY]
    return MplPath(verts, codes)


def _dms(v, pos, neg):
    d = abs(v)
    deg, minutes = int(d), round((d - int(d)) * 60)
    if minutes == 60:
        deg, minutes = deg + 1, 0
    return f"{deg}°{minutes:02d}'{pos if v >= 0 else neg}"


def _density(cells):
    """Grid kelas 0/1/2 (NaN = tanpa warna), diperhalus 16×, baris 0 = selatan."""
    idw = np.zeros((N, N))
    hit = np.zeros((N, N))
    for c in cells:
        r, k = round((c.latitude - LAT0) / GRID), round((c.longitude - LON0) / GRID)
        if 0 <= r < N and 0 <= k < N:
            idw[r, k] = c.idw_smooth or 0
            hit[r, k] = 1.0 if c.total > 0 else 0.0
    near = ndimage.gaussian_filter(hit, sigma=1.3)
    idw_f = ndimage.zoom(ndimage.gaussian_filter(idw, sigma=0.8), 16, order=3)
    near_f = ndimage.zoom(near, 16, order=3)
    cls = np.digitize(idw_f, [5, 10]).astype(float)
    cls[near_f < 0.05] = np.nan
    return cls


def render_layout(year, month, cells):
    feats = _features()
    union = feats[0][1]
    for _n, g in feats[1:]:
        union = union.union(g)
    x0, y0, x1, y1 = union.extent
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    half = max(x1 - x0, y1 - y0) / 2 * 1.08
    smap = StaticMap(cy - half, cy + half, cx - half, cx + half, zoom=12)

    W, H = 11.2, 8.3                                    # inci; peta utama MAP × MAP inci
    MAP, M = 6.45, 0.4
    mx, my = M / W, M / H
    mw, mh = MAP / W, MAP / H
    px0 = mx + mw + 0.25 / W                            # tepi kiri panel kanan
    fig = plt.figure(figsize=(W, H), dpi=150)
    fig.patch.set_facecolor("white")
    fig.add_artist(Rectangle((0.008, 0.012), 0.984, 0.976, transform=fig.transFigure, fill=False, lw=1.2, ec="#111"))

    # Kotak judul
    tax = fig.add_axes([mx, my + mh + 0.15 / H, mw, 0.95 / H])
    tax.set_xticks([]), tax.set_yticks([])
    for s in tax.spines.values():
        s.set_linewidth(1.2)
    tax.text(0.5, 0.5, f"PETA KERAPATAN SAMBARAN PETIR WILAYAH KOTA JAYAPURA\nPERIODE {BULAN[month]} TAHUN {year}",
             ha="center", va="center", fontsize=13, fontweight="bold", linespacing=1.45)

    # Peta utama (persegi)
    ax = fig.add_axes([mx, my, mw, mh])
    ax.imshow(smap.image, extent=(0, smap.width, smap.height, 0), zorder=0)
    ax.set_aspect("equal")
    city = PathPatch(_path([r for _n, g in feats for r in _rings(g)], smap), fc="white", alpha=0.55, ec="none",
                     zorder=1)
    ax.add_patch(city)
    cls = _density(cells)
    if not np.all(np.isnan(cls)):
        rgba = np.zeros(cls.shape + (4,))
        for i, (_lab, color) in enumerate(CLASSES):
            rgba[cls == i] = (*matplotlib.colors.to_rgb(color), 0.85)
        gx0, gy0 = smap.project(LAT0 + N * GRID - GRID / 2, LON0 - GRID / 2)      # sudut barat laut grid
        gx1, gy1 = smap.project(LAT0 - GRID / 2, LON0 + N * GRID - GRID / 2)      # sudut tenggara grid
        im = ax.imshow(rgba[::-1], extent=(gx0, gx1, gy1, gy0), interpolation="nearest", zorder=2)
        im.set_clip_path(PathPatch(_path([r for _n, g in feats for r in _rings(g)], smap), transform=ax.transData))
    for name, g in feats:
        ax.add_patch(PathPatch(_path(_rings(g), smap), fc="none", ec="#4b5563", lw=0.9, zorder=3))
        p = g.point_on_surface
        x, y = smap.project(p.y, p.x)
        ax.text(x, y, name, fontsize=8.5, ha="center", va="center", color="#111827", zorder=4,
                bbox=dict(boxstyle="round,pad=.15", fc="white", ec="none", alpha=0.6))
    ax.set_xlim(0, smap.width)
    ax.set_ylim(smap.height, 0)
    lon_t = np.arange(math.ceil((cx - half) * 12) / 12, cx + half, 1 / 12)
    lat_t = np.arange(math.ceil((cy - half) * 12) / 12, cy + half, 1 / 12)
    ax.set_xticks([smap.project(cy, v)[0] for v in lon_t])
    ax.set_xticklabels([_dms(v, "BT", "BB") for v in lon_t], fontsize=7)
    ax.set_yticks([smap.project(v, cx)[1] for v in lat_t])
    ax.set_yticklabels([_dms(v, "LU", "LS") for v in lat_t], fontsize=7, rotation=90, va="center")
    ax.tick_params(top=True, right=True, labeltop=True, labelright=True, length=3)
    for lab in ax.get_xticklabels(which="both"):
        lab.set_fontsize(7)
    ax.grid(color="#6b7280", lw=0.3, ls="--", alpha=0.6)
    ax.text(smap.width - 6, smap.height - 6, ATTRIBUTION, ha="right", va="bottom", fontsize=6.5,
            bbox=dict(fc="white", ec="none", alpha=0.75, pad=1.5), zorder=5)
    for s in ax.spines.values():
        s.set_linewidth(1.2)

    # Panel kanan
    pax = fig.add_axes([px0, my, 0.985 - px0 - 0.01, mh + 1.1 / H])
    pax.set_xlim(0, 1), pax.set_ylim(0, 1), pax.set_xticks([]), pax.set_yticks([])
    for s in pax.spines.values():
        s.set_linewidth(1.2)
    pw = 0.985 - px0 - 0.01
    if LOGO.exists():
        lax = fig.add_axes([px0 + pw / 2 - 0.04, 0.86, 0.08, 0.095])
        lax.imshow(Image.open(LOGO)), lax.axis("off")
    pax.text(0.5, 0.815, "STASIUN GEOFISIKA\nKELAS I JAYAPURA", ha="center", va="center", fontsize=11,
             fontweight="bold", linespacing=1.3)
    pax.text(0.5, 0.748, "U", ha="center", fontsize=11, fontweight="bold")
    pax.add_patch(FancyArrow(0.5, 0.665, 0, 0.045, width=0.02, head_width=0.07, head_length=0.03, color="#111"))

    # Skala batang (km)
    km_per_px = (2 * half * 111.32 * math.cos(math.radians(cy))) / smap.width
    pan_w_in = pax.get_position().width * W
    bar_km = 12
    bar_frac = (bar_km / km_per_px) / smap.width * MAP / pan_w_in
    bx = 0.5 - bar_frac / 2
    for i in range(4):
        pax.add_patch(Rectangle((bx + bar_frac * i / 4, 0.605), bar_frac / 4, 0.012,
                                fc="#111" if i % 2 == 0 else "white", ec="#111", lw=0.8))
    for i, km in enumerate((0, 3, 6, 12)):
        pax.text(bx + bar_frac * km / 12, 0.625, str(km), ha="center", fontsize=7.5)
    pax.text(bx + bar_frac, 0.588, "Kilometer", ha="right", fontsize=7)

    pax.text(0.06, 0.54, "Legenda", fontsize=12, fontweight="bold")
    for i, (lab, color) in enumerate(CLASSES):
        y = 0.50 - i * 0.035
        pax.add_patch(Rectangle((0.08, y), 0.09, 0.022, fc=color, ec="#6b7280", lw=0.6))
        pax.text(0.21, y + 0.011, lab, va="center", fontsize=9)
    y = 0.50 - len(CLASSES) * 0.035
    pax.add_patch(Rectangle((0.08, y), 0.09, 0.022, fc="none", ec="#4b5563", lw=0.9))
    pax.text(0.21, y + 0.011, "Batas kecamatan", va="center", fontsize=9)

    pax.text(0.06, 0.345, f"Sumber Data :\nData Listrik Udara {BULAN_TITLE[month]} {year}\n"
             "Stasiun Geofisika Kelas I Jayapura", fontsize=8.5, va="top", linespacing=1.4)
    pax.text(0.06, 0.255, "Inset Peta", fontsize=9.5, fontweight="bold")

    # Inset Papua
    iax = fig.add_axes([px0 + 0.012, my + 0.012, pw - 0.024, 0.2])
    ismap = StaticMap(-9.3, 0.3, 130.0, 142.0, zoom=6)
    iax.imshow(ismap.image, extent=(0, ismap.width, ismap.height, 0))
    rx0, ry0 = ismap.project(cy + half, cx - half)
    rx1, ry1 = ismap.project(cy - half, cx + half)
    iax.add_patch(Rectangle((rx0 - 3, ry0 - 3), rx1 - rx0 + 6, ry1 - ry0 + 6, fill=False, ec="#dc2626", lw=1.6))
    ix, iy = ismap.project(-4.3, 137.5)
    iax.text(ix, iy, "Papua", fontsize=9, ha="center")
    iax.set_xlim(0, ismap.width), iax.set_ylim(ismap.height, 0)
    iax.set_xticks([]), iax.set_yticks([])
    iax.set_aspect("equal")
    iax.set_anchor("C")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor="white")
    plt.close(fig)
    return buf.getvalue()
