"""Bangun layer sesar, palung, dan megathrust PuSGeN 2024 untuk peta Leaflet dan petunjuk "Sumber terdekat".

Sumber: shapefile resmi PuSGeN 2024 (Peta Sumber dan Bahaya Gempa Indonesia Tahun 2024) di
scripts/geodata/pusgen2024/:
  * PusGeN2024_Shallow_Crustal_v5_12.zip  sesar kerak dangkal, 402 segmen (Name, Segment, Mmax, Type, ...)
  * 2024_Megathrust_v2.zip                 14 poligon sumber megathrust dan 5 garis palung subduksi

Keluaran (format sama dengan berkas lama, jadi kode Leaflet tetap):
  * indofaults.js  `var indoFaults = [FeatureCollection];`  (gempa/static/gjson dan repository/static/...)
  * subduksi.js    `var subDuksi = [FeatureCollection];`    palung subduksi 2024
  * gempa/data/pusgen2024_megathrust.json                   poligon megathrust (dipakai server)

    python scripts/geodata/pusgen_faults_js.py

Butuh ogr2ogr (GDAL).
"""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(__file__).with_name("pusgen2024")
CRUSTAL = ("PusGeN2024_Shallow_Crustal_v5_12.zip", "PusGeN2024_Shallow_Crustal_v5_12.shp")
MEGATHRUST = ("2024_Megathrust_v2.zip", "2024_Megathrust_v2/2024_Megathrust_v2.shp")
TRENCH = ("2024_Megathrust_v2.zip", "2024_Subduction trench_v2/2024_Subduction trench_v2.shp")
JS_DIRS = [ROOT / "gempa/static/gjson", ROOT / "repository/static/repository/js"]
MEGATHRUST_OUT = ROOT / "gempa/data/pusgen2024_megathrust.json"
CREDIT = "PuSGeN 2024, Peta Sumber dan Bahaya Gempa Indonesia Tahun 2024"


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
        faults.append({"type": "Feature", "geometry": f["geometry"], "properties": {
            "nama": (p.get("Name") or "").strip(), "segmen": (p.get("Segment") or "").strip(),
            "tipe": jenis(p.get("Type") or ""), "kode": (p.get("Type") or "").strip(),
            "mmax": number(p.get("Mmax")), "sliprate": number(p.get("Sliprate_m")),
            "panjang_km": number(p.get("Length_km")), "wilayah": (p.get("Region") or "").strip(),
        }})
    write_js("indofaults.js", "indoFaults", collection("pusgen2024_sesar_aktif", faults))

    trenches = [{"type": "Feature", "geometry": f["geometry"],
                 "properties": {"nama": (f["properties"].get("TrenchName") or "").strip(),
                                "keterangan": (f["properties"].get("Remarks") or "").strip()}}
                for f in read_layer(*TRENCH)]
    write_js("subduksi.js", "subDuksi", collection("pusgen2024_palung_subduksi", trenches))

    zones = [{"type": "Feature", "geometry": f["geometry"],
              "properties": {"nama": (f["properties"].get("Name") or "").strip()}}
             for f in read_layer(*MEGATHRUST, precision=3)]
    MEGATHRUST_OUT.parent.mkdir(exist_ok=True)
    MEGATHRUST_OUT.write_text(json.dumps(collection("pusgen2024_megathrust", zones), ensure_ascii=False,
                                         separators=(",", ":")))
    print(f"{len(faults)} segmen sesar, {len(trenches)} palung, {len(zones)} zona megathrust")


if __name__ == "__main__":
    main()
