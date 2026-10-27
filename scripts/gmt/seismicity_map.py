"""Peta seismisitas bergaya GMT untuk Event Browser (dijalankan dengan venv PyGMT terpisah).

Pemakaian:  python seismicity_map.py input.json output.png

input.json:
  title, subtitle            judul peta
  region   [W, E, S, N]      batas peta (derajat)
  events   [{lon, lat, depth, mag}]
  felt     [{lon, lat, mag}] gempabumi dirasakan (bintang)
  faults, subduction         path berkas .js/.geojson (opsional)
  source_label               teks sumber data gempabumi

Relief: GMT Earth Relief (SRTM15+, Tozer dkk. 2019) dengan iluminasi; laut diberi warna datar.
"""
import json
import re
import sys
import tempfile
from pathlib import Path

import pygmt

DEPTH_CLASSES = [("Dangkal (< 60 km)", 0, 60, "red"), ("Menengah (60-300 km)", 60, 300, "yellow"),
                 ("Dalam (> 300 km)", 300, 10_000, "green3")]
SEA = "#a9d3ea"


def mag_size(m):
    """Diameter simbol (cm) menurut magnitudo."""
    return round(0.10 + 0.035 * max(m, 1.0) ** 1.6, 3)


def load_geojson(path):
    """Baca GeoJSON, termasuk berkas .js berbentuk `var x = [ {FeatureCollection} ];`."""
    text = Path(path).read_text()
    if not path.endswith((".json", ".geojson")):
        text = text[text.index("=") + 1:].strip().rstrip(";")
    data = json.loads(text)
    return data if isinstance(data, list) else [data]


def write_lines(collections, out, region):
    """Tulis LineString/MultiLineString yang memotong region ke berkas multi-segmen GMT."""
    w, e, s, n = region
    n_seg = 0
    with open(out, "w") as f:
        for fc in collections:
            for feat in fc.get("features", []):
                g = feat.get("geometry") or {}
                parts = {"LineString": [g.get("coordinates")], "MultiLineString": g.get("coordinates"),
                         "Polygon": g.get("coordinates"), "MultiPolygon": [r for p in g.get("coordinates", []) for r in p]
                         }.get(g.get("type"), [])
                for line in parts or []:
                    if not line or not any(w - 1 <= p[0] <= e + 1 and s - 1 <= p[1] <= n + 1 for p in line):
                        continue
                    f.write(">\n" + "".join(f"{p[0]} {p[1]}\n" for p in line))
                    n_seg += 1
    return n_seg


def main(inp, out):
    cfg = json.loads(Path(inp).read_text())
    region = cfg["region"]
    events = sorted(cfg.get("events", []), key=lambda ev: -ev["mag"])      # besar dulu, kecil di atas
    felt = cfg.get("felt", [])
    tmp = Path(tempfile.mkdtemp(prefix="gmt_seis_"))

    pygmt.config(MAP_FRAME_TYPE="fancy", MAP_FRAME_WIDTH="5p", FORMAT_GEO_MAP="ddd", FONT_ANNOT_PRIMARY="9p",
                 FONT_LABEL="9p", MAP_TITLE_OFFSET="6p", FONT_TITLE="14p,Helvetica-Bold", PS_MEDIA="A3")
    fig = pygmt.Figure()
    width = 17.0
    proj = f"M{width}c"
    span = max(region[1] - region[0], region[3] - region[2])
    res = "30s" if span <= 6 else "01m" if span <= 20 else "02m"
    relief = pygmt.datasets.load_earth_relief(resolution=res, region=region)
    pygmt.makecpt(cmap="dem2", series=[0, 5000])
    fig.grdimage(relief, region=region, projection=proj, shading="+a315+nt0.7", cmap=True,
                 frame=["WSne", "xa2f1", "ya2f1"])
    fig.coast(water=SEA, shorelines="0.25p,gray30", borders="1/0.6p,black,-", resolution="h")
    fig.text(position="TC", text=cfg.get("title", ""), offset="0c/0.75c", no_clip=True,
             font="14p,Helvetica-Bold,black", justify="BC")

    files = {}
    for key, pen in (("subduction", "1.6p,purple"), ("faults", "0.45p,black")):
        if cfg.get(key):
            p = tmp / f"{key}.gmt"
            if write_lines(load_geojson(cfg[key]), p, region):
                files[key] = p
                fig.plot(data=str(p), pen=pen)

    if events:
        for label, lo, hi, color in DEPTH_CLASSES:
            sel = [ev for ev in events if lo <= ev["depth"] < hi]
            if sel:
                fig.plot(x=[ev["lon"] for ev in sel], y=[ev["lat"] for ev in sel],
                         size=[mag_size(ev["mag"]) for ev in sel], style="c", fill=color, pen="0.3p,black",
                         transparency=10)
    if felt:
        fig.plot(x=[f["lon"] for f in felt], y=[f["lat"] for f in felt], style="a0.55c", fill="red",
                 pen="0.8p,black")

    from pygmt.params import Box, Position
    fig.directional_rose(position=Position("TL", cstype="inside", offset=(0.4, 0.4)), width="1.5c", fancy=2,
                         labels=["B", "T", "S", "U"])
    fig.scalebar(length="200k", position=Position("BR", cstype="inside", offset=(0.5, 2.6)), fancy=True,
                 label="km", scale_loc=True, box=Box(fill="white@15", pen="0.3p,gray40", clearance="4p"))

    # Ringkasan (kanan atas)
    mags = [ev["mag"] for ev in events]
    lines = [cfg.get("subtitle", ""), f"Jumlah gempabumi: {len(events)}"]
    if mags:
        lines += [f"Magnitudo terbesar: {max(mags):.1f}", f"Magnitudo terkecil: {min(mags):.1f}",
                  f"M >= 5,0: {sum(m >= 5 for m in mags)}"]
    lines.append(f"Gempabumi dirasakan: {len(felt)}")
    info = tmp / "info.txt"
    info.write_text("\n".join([f"L 9p,Helvetica-Bold,firebrick L {lines[0]}"]
                              + [f"L 8.5p,Helvetica,black L {t}" for t in lines[1:]]) + "\n")
    fig.legend(spec=str(info), position="jTR+o0.3c/0.3c", box="+gwhite@10+p0.4p,gray40")

    # Legenda
    leg = tmp / "legend.txt"
    rows = ["H 10p,Helvetica-Bold Legenda", "D 0p 0.4p", "N 1"]
    for label, _lo, _hi, color in DEPTH_CLASSES:
        rows.append(f"S 0.3c c 0.28c {color} 0.3p,black 0.7c {label}")
    rows += ["G 0.1c", "N 4"]
    for m in (3, 4, 5, 6):
        rows.append(f"S 0.3c c {mag_size(m)}c white 0.3p,black 0.7c M{m}")
    rows += ["G 0.15c", "N 1"]
    rows.append("S 0.3c a 0.42c red 0.8p,black 0.7c Gempabumi dirasakan")
    if "faults" in files:
        rows.append("S 0.3c - 0.5c - 0.45p,black 0.7c Sesar")
    if "subduction" in files:
        rows.append("S 0.3c - 0.5c - 1.6p,purple 0.7c Zona subduksi")
    leg.write_text("\n".join(rows) + "\n")
    fig.legend(spec=str(leg), position="jBL+o0.3c/0.3c+w5.2c", box="+gwhite@10+p0.4p,gray40+r")

    # Inset Indonesia
    with fig.inset(position="jBR+o0.3c/0.3c+w4.4c/1.75c", box="+gwhite+p0.6p,black"):
        fig.coast(region=[94, 146, -11.5, 7], projection="M4.4c", land="gray75", water="white",
                  shorelines="0.1p,gray40", resolution="l")
        w, e, s, n = region
        fig.plot(x=[w, e, e, w, w], y=[s, s, n, n, s], pen="1p,red")

    fig.text(position="BC", text=cfg.get("source_label", ""), offset="0c/-1.25c", no_clip=True,
             font="7p,Helvetica,gray25", justify="TC")
    fig.text(position="BC", text="Relief: GMT Earth Relief (Tozer dkk., 2019); sesar: PuSGeN 2024; garis pantai: GSHHG",
             offset="0c/-1.6c", no_clip=True, font="7p,Helvetica,gray25", justify="TC")
    fig.savefig(out, dpi=200, crop=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
