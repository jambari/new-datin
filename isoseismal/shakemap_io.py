"""Baca keluaran ShakeMap v3 dari .50 (output/grid.xml dan output/stationlist.xml).

grid.xml (±7 MB) diringkas menjadi grid MMI float16 dalam berkas .npz (±100–300 KB):
    mmi      array (nlat, nlon), baris pertama = lintang paling utara
    bounds   [lon_min, lat_min, lon_max, lat_max]
"""
import io
import math
import re
import xml.etree.ElementTree as ET

import numpy as np

_NS = re.compile(r"^\{[^}]*\}")


def _tag(el):
    return _NS.sub("", el.tag)


def parse_grid(source):
    """(info event, mmi 2-D north-up, bounds) dari grid.xml (path atau file-like)."""
    event, spec, fields, text = {}, {}, {}, None
    for _ev, el in ET.iterparse(source, events=("end",)):
        name = _tag(el)
        if name == "event":
            event = dict(el.attrib)
        elif name == "grid_specification":
            spec = dict(el.attrib)
        elif name == "grid_field":
            fields[el.attrib["name"].upper()] = int(el.attrib["index"]) - 1
        elif name == "grid_data":
            text = el.text or ""
            el.clear()
    if not spec or text is None or "MMI" not in fields:
        raise ValueError("grid.xml tidak lengkap (grid_specification / grid_data / kolom MMI)")
    nlon, nlat = int(spec["nlon"]), int(spec["nlat"])
    data = np.loadtxt(io.StringIO(text), dtype=np.float32, ndmin=2)
    if data.shape[0] != nlon * nlat:
        raise ValueError(f"grid_data {data.shape[0]} baris, seharusnya {nlon * nlat}")
    lon, lat = data[:, fields["LON"]], data[:, fields["LAT"]]
    mmi = data[:, fields["MMI"]]
    # ShakeMap menulis baris dari utara ke selatan, barat ke timur; urutkan ulang agar pasti.
    order = np.lexsort((lon, -lat))
    mmi = mmi[order].reshape(nlat, nlon)
    bounds = [float(spec["lon_min"]), float(spec["lat_min"]), float(spec["lon_max"]), float(spec["lat_max"])]
    info = {
        "magnitude": _float(event.get("magnitude")),
        "depth": _float(event.get("depth")),
        "latitude": _float(event.get("lat")),
        "longitude": _float(event.get("lon")),
        "lokasi": event.get("event_description", ""),
    }
    return info, mmi, bounds


def _float(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def grid_to_npz(mmi, bounds):
    buf = io.BytesIO()
    np.savez_compressed(buf, mmi=mmi.astype(np.float16), bounds=np.asarray(bounds, dtype=np.float64))
    return buf.getvalue()


def load_npz(fileobj):
    with np.load(fileobj) as z:
        return z["mmi"].astype(np.float32), [float(v) for v in z["bounds"]]


_OBS_NAME = re.compile(r"\s*\(intensity[^)]*\)\s*$", re.I)


def parse_stations(source):
    """(stasiun akselerograf, titik intensitas teramati) dari stationlist.xml.

    Stasiun: kode, posisi, jarak, MMI instrumental, PGA (%g), PGV (cm/s); nilai berbendera
    (flag selain 0/kosong, mis. 'T' = outlier) tidak dipakai.
    Titik teramati: laporan dirasakan yang dimasukkan ke ShakeMap (insttype="Observed",
    nama "Depapre (Intensity 2)"), sudah berkoordinat.
    """
    stations, observed = [], []
    root = ET.parse(source).getroot()
    for st in root.iter():
        if _tag(st) != "station":
            continue
        a = st.attrib
        lat, lon = _float(a.get("lat")), _float(a.get("lon"))
        if lat is None or lon is None:
            continue
        mmi = _float(a.get("intensity"))
        if a.get("insttype", "").lower() == "observed" or a.get("netid", "").upper() == "INTENSITY":
            if mmi is not None:
                observed.append({
                    "place": _OBS_NAME.sub("", a.get("name", "")).strip() or a.get("code", ""),
                    "lat": round(lat, 4), "lon": round(lon, 4), "mmi": round(mmi, 1),
                    "source": "shakemap",
                })
            continue
        flagged = a.get("intensity_flag", "") not in ("", "0")
        pga = pgv = None
        for comp in st:
            for amp in comp:
                kind = _tag(amp)
                if kind not in ("acc", "vel") or amp.attrib.get("flag", "0") not in ("", "0"):
                    continue
                value = _float(amp.attrib.get("value"))
                if value is None:
                    continue
                if kind == "acc":
                    pga = value if pga is None else max(pga, value)
                else:
                    pgv = value if pgv is None else max(pgv, value)
        stations.append({
            "code": a.get("code", ""),
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "dist_km": round(_float(a.get("dist")) or 0, 1),
            "mmi": None if flagged or mmi is None else round(mmi, 1),
            "pga": None if pga is None else round(pga, 4),
            "pgv": None if pgv is None else round(pgv, 4),
        })
    stations.sort(key=lambda s: s["dist_km"])
    observed.sort(key=lambda o: -o["mmi"])
    return stations, observed
