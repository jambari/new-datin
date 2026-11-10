"""Simpan hasil ShakeMap dari .50 dan gambar peta isoseismal."""
import datetime
import logging

import numpy as np
from django.core.files.base import ContentFile
from django.utils import timezone
from matplotlib.path import Path as MplPath

from .felt import collect_felt, regions
from .models import IsoseismalMap
from .shakemap_io import grid_to_npz, load_npz, parse_grid, parse_stations

log = logging.getLogger(__name__)
WIB = datetime.timezone(datetime.timedelta(hours=7))


def wib_to_utc(wib_id):
    t = datetime.datetime.strptime(wib_id[:14], "%Y%m%d%H%M%S")
    return t.replace(tzinfo=WIB).astimezone(datetime.timezone.utc)


def store_shakemap(wib_id, grid_path=None, stationlist_path=None):
    """Buat/perbarui IsoseismalMap dari grid.xml & stationlist.xml satu kejadian. Kembalikan objeknya."""
    obj = IsoseismalMap.objects.filter(wib_id=wib_id).first() or IsoseismalMap(wib_id=wib_id)
    obj.event_time = wib_to_utc(wib_id)
    if grid_path:
        info, mmi, bounds = parse_grid(grid_path)
        for field in ("latitude", "longitude", "magnitude", "depth"):
            if info.get(field) is not None:
                setattr(obj, field, info[field])
        obj.lokasi = info.get("lokasi") or obj.lokasi
        if obj.grid:
            obj.grid.delete(save=False)
        obj.grid.save(f"{wib_id}.npz", ContentFile(grid_to_npz(mmi, bounds)), save=False)
        obj.wilayah = wilayah_mmi(mmi, bounds)
    if stationlist_path:
        obj.stations, obj.observed = parse_stations(stationlist_path)
    for field in ("latitude", "longitude", "magnitude", "depth"):
        if getattr(obj, field) is None:
            raise ValueError(f"{wib_id}: {field} tidak diketahui (grid.xml belum ada)")
    if not obj.slug:
        obj.slug = obj.build_slug()
    obj.save()
    return obj


def wilayah_mmi(mmi, bounds):
    """[{name, mmi}] MMI grid tertinggi di dalam tiap kabupaten/kota Papua, menurun."""
    lon_min, lat_min, lon_max, lat_max = bounds
    nlat, nlon = mmi.shape
    lons = np.linspace(lon_min, lon_max, nlon)
    lats = np.linspace(lat_max, lat_min, nlat)
    out = []
    for name, geom, bb in regions("kabupaten"):
        if bb[2] < lon_min or bb[0] > lon_max or bb[3] < lat_min or bb[1] > lat_max:
            continue
        ci = np.nonzero((lons >= bb[0]) & (lons <= bb[2]))[0]
        ri = np.nonzero((lats >= bb[1]) & (lats <= bb[3]))[0]
        if not ci.size or not ri.size:
            continue
        LON, LAT = np.meshgrid(lons[ci], lats[ri])
        pts = np.column_stack([LON.ravel(), LAT.ravel()])
        inside = np.zeros(len(pts), dtype=bool)
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        for poly in polys:
            inside |= MplPath(np.asarray(poly[0], dtype=float)).contains_points(pts)
        if not inside.any():
            continue
        value = float(mmi[np.ix_(ri, ci)].ravel()[inside].max())
        label = "Kota " + name[5:].title() if name.startswith("KOTA ") else "Kab. " + name.title()
        out.append({"name": label, "mmi": round(value, 1)})
    out.sort(key=lambda w: -w["mmi"])
    return out


def refresh_felt(obj):
    """Cari ulang laporan dirasakan; True bila berubah."""
    felt, text, sources = collect_felt(obj.event_time, obj.latitude, obj.longitude, obj.observed)
    changed = (felt, text, sources) != (obj.felt, obj.felt_text, obj.felt_sources)
    obj.felt, obj.felt_text, obj.felt_sources = felt, text, sources
    return changed


def generate(obj, force=False):
    """Gambar ulang peta bila ada laporan dirasakan. Kembalikan teks status singkat."""
    from .layout import render_map

    changed = refresh_felt(obj)
    if not obj.felt:
        obj.note = "Belum ada laporan dirasakan."
        obj.save(update_fields=["felt", "felt_text", "felt_sources", "note", "updated_at"])
        return "skip: tidak dirasakan"
    if obj.image and not changed and not force:
        obj.save(update_fields=["felt", "felt_text", "felt_sources", "updated_at"])
        return "skip: tidak berubah"
    mmi = bounds = None
    if obj.grid:
        try:
            with obj.grid.open("rb") as fh:
                mmi, bounds = load_npz(fh)
        except (OSError, ValueError) as exc:
            log.warning("isoseismal %s: grid tidak terbaca: %s", obj.wib_id, exc)
    png = render_map(obj, mmi, bounds)
    if obj.image:
        obj.image.delete(save=False)
    obj.image.save(f"{obj.slug}.png", ContentFile(png), save=False)
    obj.generated_at = timezone.now()
    obj.note = ""
    obj.save()
    return f"digambar ({len(obj.felt)} tempat, {len(obj.stations)} stasiun)"
