"""Bangun layer sesar, palung, dan megathrust PuSGeN 2024 untuk peta Leaflet dan petunjuk "Sumber terdekat".

Sumber: shapefile resmi PuSGeN 2024 (Peta Sumber dan Bahaya Gempa Indonesia Tahun 2024) di
scripts/geodata/pusgen2024/:
  * PusGeN2024_Shallow_Crustal_v5_12.zip  sesar kerak dangkal, 402 segmen (Name, Segment, Mmax, Type, ...)
  * 2024_Megathrust_v2.zip                 14 poligon sumber megathrust dan 5 garis palung subduksi

Keluaran (format sama dengan berkas lama, jadi kode Leaflet tetap):
  * indofaults.js  `var indoFaults = [FeatureCollection];`  (gempa/static/gjson dan repository/static/...)
  * subduksi.js    `var subDuksi = [FeatureCollection];`    palung subduksi 2024
  * gempa/data/pusgen2024_megathrust.json                   poligon megathrust (dipakai server)
  * scripts/geodata/pusgen2024/gmt/*.gmt                    berkas GMT untuk buat_peta.sh (peta episenter)

Garis sesar naik/turun dan palung diarahkan sehingga sisi gigi (hanging wall / lempeng atas) selalu di KIRI
arah garis, dan diberi properti "gigi": true. Leaflet (gempa/static/js/pusgen_layer.js) dan GMT
(`gmt plot -Sf...+l+t`) cukup menggambar gigi di sisi kiri.

    python scripts/geodata/pusgen_faults_js.py

Butuh ogr2ogr (GDAL).
"""
import json
import math
import re
import subprocess
from pathlib import Path

from simplify_geojson_js import simplify_line

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(__file__).with_name("pusgen2024")
CRUSTAL = ("PusGeN2024_Shallow_Crustal_v5_12.zip", "PusGeN2024_Shallow_Crustal_v5_12.shp")
MEGATHRUST = ("2024_Megathrust_v2.zip", "2024_Megathrust_v2/2024_Megathrust_v2.shp")
TRENCH = ("2024_Megathrust_v2.zip", "2024_Subduction trench_v2/2024_Subduction trench_v2.shp")
JS_DIRS = [ROOT / "gempa/static/gjson", ROOT / "repository/static/repository/js"]
MEGATHRUST_OUT = ROOT / "gempa/data/pusgen2024_megathrust.json"
GMT_OUT = SRC / "gmt"
GMT_SIMPLIFY = 0.015     # derajat (±1,5 km): ruas sangat pendek membuat arah simbol -Sf GMT melenceng
CREDIT = "PuSGeN 2024, Peta Sumber dan Bahaya Gempa Indonesia Tahun 2024"
ARAH = {"N": (0, 1), "S": (0, -1), "E": (1, 0), "W": (-1, 0)}
# sisi lempeng atas (overriding) tiap palung subduksi 2024
PALUNG_ARAH = {"Sumatra-Jawa": "NE", "Papua": "S", "Philippine": "W", "Cotobato": "E", "North Arm Sulawesi": "S"}


def read_layer(zip_name, shp, precision=4):
    out = subprocess.run(
        ["ogr2ogr", "-f", "GeoJSON", "/vsistdout/", f"/vsizip/{SRC / zip_name}/{shp}", "-dim", "2",
         "-t_srs", "EPSG:4326", "-lco", f"COORDINATE_PRECISION={precision}", "-lco", "RFC7946=YES"],
        check=True, capture_output=True, text=True).stdout
    return json.loads(out)["features"]


def jenis(kode):
    """Kode Type PuSGeN ('SS-LL90', 'R45S', 'N60E', 'RR45S') -> geser/naik/turun."""
    kode = kode.strip().upper()
    return "geser" if kode.startswith("SS") else "turun" if kode.startswith("N") else "naik"


def arah_dip(kode):
    """'R45S' -> (0, -1), 'N60NE' -> NE, 'R45N-W' -> NW; None bila kode tanpa arah ('R45', 'SS90')."""
    m = re.search(r"\d([NSEW]{1,2})$", kode.strip().upper().replace("-", ""))
    if not m:
        return None
    x = sum(ARAH[c][0] for c in m.group(1))
    y = sum(ARAH[c][1] for c in m.group(1))
    n = math.hypot(x, y)
    return (x / n, y / n)


def _parts(geometry):
    return [geometry["coordinates"]] if geometry["type"] == "LineString" else geometry["coordinates"]


def orient_left(geometry, dip):
    """Balik arah garis bila perlu agar sisi `dip` ada di kiri (suara berbobot panjang tiap ruas)."""
    vote = 0.0
    for part in _parts(geometry):
        for (x1, y1), (x2, y2) in zip(part, part[1:]):
            k = math.cos(math.radians((y1 + y2) / 2))
            dx, dy = (x2 - x1) * k, y2 - y1
            vote += -dy * dip[0] + dx * dip[1]          # kiri = (-dy, dx), dikali panjang ruas
    if vote < 0:
        parts = [list(reversed(p)) for p in reversed(_parts(geometry))]
        geometry = {"type": geometry["type"], "coordinates": parts[0] if geometry["type"] == "LineString" else parts}
    return geometry


def on_trench(geometry, trenches, km=5.0, share=0.9):
    """True bila ≥ `share` titik garis berjarak < `km` dari garis palung mana pun."""
    segs = [(a, b) for t in trenches for part in _parts(t["geometry"]) for a, b in zip(part, part[1:])]
    pts = [c for part in _parts(geometry) for c in part]

    def dist(lon, lat):
        k = math.cos(math.radians(lat))
        best = float("inf")
        for (x1, y1), (x2, y2) in segs:
            ax, ay, dx, dy = (x1 - lon) * k, y1 - lat, (x2 - x1) * k, y2 - y1
            t = max(0.0, min(1.0, -(ax * dx + ay * dy) / ((dx * dx + dy * dy) or 1)))
            best = min(best, math.hypot(ax + t * dx, ay + t * dy))
        return best * 111.2

    return sum(dist(x, y) < km for x, y in pts) >= share * len(pts)


def write_gmt(name, features, header, tol=0.0):
    lines = [f"# {header}", f"# {CREDIT}; dibuat oleh scripts/geodata/pusgen_faults_js.py"]
    for f in features:
        label = " – ".join(x for x in (f["properties"]["nama"], f["properties"].get("segmen", "")) if x)
        for part in _parts(f["geometry"]):
            part = simplify_line(part, tol, 4)                  # juga membuang titik kembar berurutan
            if len(part) < 2:
                continue
            lines.append(f'> -L"{label}"')
            lines += [f"{x:.4f}\t{y:.4f}" for x, y in part]
    GMT_OUT.mkdir(exist_ok=True)
    (GMT_OUT / name).write_text("\n".join(lines) + "\n")


def number(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def collection(name, features):
    return {"type": "FeatureCollection", "name": name, "sumber": CREDIT, "features": features}


def write_js(filename, var, data):
    text = f"var {var} = [" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "];\n"
    for d in JS_DIRS:
        (d / filename).write_text(text)


def main():
    faults = []
    for f in read_layer(*CRUSTAL):
        p = f["properties"]
        kode = (p.get("Type") or "").strip()
        props = {
            "nama": (p.get("Name") or "").strip(), "segmen": (p.get("Segment") or "").strip(),
            "tipe": jenis(kode), "kode": kode,
            "mmax": number(p.get("Mmax")), "sliprate": number(p.get("Sliprate_m")),
            "panjang_km": number(p.get("Length_km")), "wilayah": (p.get("Region") or "").strip(),
        }
        geometry, dip = f["geometry"], arah_dip(kode)
        if props["tipe"] != "geser" and dip:
            geometry, props["gigi"] = orient_left(geometry, dip), True
        faults.append({"type": "Feature", "geometry": geometry, "properties": props})

    trenches = []
    for f in read_layer(*TRENCH):
        nama = (f["properties"].get("TrenchName") or "").strip()
        side = PALUNG_ARAH[nama]
        dip = arah_dip(f"T0{side}")
        trenches.append({"type": "Feature", "geometry": orient_left(f["geometry"], dip),
                         "properties": {"nama": nama, "tipe": "subduksi", "gigi": True,
                                        "keterangan": (f["properties"].get("Remarks") or "").strip()}})
    write_js("subduksi.js", "subDuksi", collection("pusgen2024_palung_subduksi", trenches))

    # sesar yang berimpit dengan palung (North Papua Thrust): gigi digambar oleh layer palung saja
    for f in faults:
        if f["properties"].get("gigi") and on_trench(f["geometry"], trenches):
            f["properties"]["palung"] = True
            print(f"berimpit palung: {f['properties']['nama']} – {f['properties']['segmen']}")
    write_js("indofaults.js", "indoFaults", collection("pusgen2024_sesar_aktif", faults))

    bergigi = [f for f in faults if f["properties"].get("gigi") and not f["properties"].get("palung")]
    write_gmt("sesar_geser.gmt", [f for f in faults if f not in bergigi],
              "Sesar geser, sesar tanpa arah kemiringan, dan sesar yang berimpit palung (garis polos)")
    write_gmt("sesar_naik.gmt", [f for f in bergigi if f["properties"]["tipe"] == "naik"],
              "Sesar naik, sisi hanging wall di kiri: gmt plot -Sf...+l+t", GMT_SIMPLIFY)
    write_gmt("sesar_turun.gmt", [f for f in bergigi if f["properties"]["tipe"] == "turun"],
              "Sesar turun, sisi hanging wall di kiri: gmt plot -Sf...+l+f", GMT_SIMPLIFY)
    write_gmt("subduksi.gmt", trenches, "Palung subduksi, lempeng atas di kiri: gmt plot -Sf...+l+t", GMT_SIMPLIFY)

    zones = [{"type": "Feature", "geometry": f["geometry"],
              "properties": {"nama": (f["properties"].get("Name") or "").strip()}}
             for f in read_layer(*MEGATHRUST, precision=3)]
    MEGATHRUST_OUT.parent.mkdir(exist_ok=True)
    MEGATHRUST_OUT.write_text(json.dumps(collection("pusgen2024_megathrust", zones), ensure_ascii=False,
                                         separators=(",", ":")))
    print(f"{len(faults)} segmen sesar, {len(trenches)} palung, {len(zones)} zona megathrust")


if __name__ == "__main__":
    main()
