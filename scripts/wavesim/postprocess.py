"""Turn SPECFEM3D surface-movie output into web assets (Python 3.8, .51).

Reads OUTPUT_FILES/moviedataNNNNNN (vertical surface velocity per frame),
shakingdata (peak displacement / velocity / acceleration) and the *.semv
station seismograms, and writes to RUN_DIR/web/:

  frames/fNNN.png  transparent overlay frames of vertical velocity on a
                   regular lon/lat grid (Leaflet imageOverlay)
  pgv.png          peak ground velocity overlay (log colour scale)
  result.json      bounds, frame times, colour scales, seismograms, stats
"""
import glob
import json
import math
import os

import numpy as np
from matplotlib import cm
from PIL import Image
from scipy.interpolate import griddata
from scipy.io import FortranFile

GRID = 360            # output overlay resolution (pixels per side)
A = 6378137.0         # WGS84, as in SPECFEM utm_geo.f90
F = 1 / 298.257223563
K0 = 0.9996


def utm_to_lonlat(x, y, zone):
    """Inverse UTM (arrays). Negative zone = southern hemisphere (SPECFEM convention)."""
    e2 = F * (2 - F)
    ep2 = e2 / (1 - e2)
    x = np.asarray(x, dtype=float) - 500000.0
    y = np.asarray(y, dtype=float)
    if zone < 0:
        y = y - 10000000.0
    lon0 = math.radians((abs(zone) - 1) * 6 - 180 + 3)
    m = y / K0
    mu = m / (A * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    phi1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * np.sin(2 * mu)
            + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * np.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * np.sin(6 * mu))
    n1 = A / np.sqrt(1 - e2 * np.sin(phi1) ** 2)
    t1 = np.tan(phi1) ** 2
    c1 = ep2 * np.cos(phi1) ** 2
    r1 = A * (1 - e2) / (1 - e2 * np.sin(phi1) ** 2) ** 1.5
    d = x / (n1 * K0)
    lat = phi1 - (n1 * np.tan(phi1) / r1) * (
        d ** 2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2) * d ** 6 / 720)
    lon = lon0 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6
                  + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2 + 24 * t1 ** 2) * d ** 5 / 120
                  ) / np.cos(phi1)
    return np.degrees(lon), np.degrees(lat)


def _read_records(path, n=6):
    f = FortranFile(path, "r")
    out = [f.read_reals(np.float32) for _ in range(n)]
    f.close()
    return out


class Grid:
    """Interpolates scattered surface points onto a regular lon/lat grid."""

    def __init__(self, x, y, zone):
        lon, lat = utm_to_lonlat(x, y, zone)
        self.pts = np.column_stack([lon, lat])
        # Drop the outer 4% on each side: Stacey boundaries leave edge artefacts.
        lo0, lo1, la0, la1 = lon.min(), lon.max(), lat.min(), lat.max()
        pad_lo, pad_la = 0.04 * (lo1 - lo0), 0.04 * (la1 - la0)
        self.bounds = [[la0 + pad_la, lo0 + pad_lo], [la1 - pad_la, lo1 - pad_lo]]
        self.glon, self.glat = np.meshgrid(
            np.linspace(lo0 + pad_lo, lo1 - pad_lo, GRID),
            np.linspace(la1 - pad_la, la0 + pad_la, GRID))   # row 0 = north

    def __call__(self, values):
        return griddata(self.pts, values, (self.glon, self.glat), method="linear")


def _png(rgba, path):
    Image.fromarray((np.clip(rgba, 0, 1) * 255).astype(np.uint8), "RGBA").save(path, optimize=True)


def render_frames(out, grid, frames, vmax):
    """Vertical velocity, compressed with asinh so the far field stays visible."""
    cmap = cm.get_cmap("seismic")
    a = vmax / 10.0
    norm = math.asinh(vmax / a)
    os.makedirs(os.path.join(out, "frames"), exist_ok=True)
    for i, uz in enumerate(frames):
        g = np.nan_to_num(grid(uz))
        s = np.arcsinh(g / a) / norm                      # -1..1
        rgba = cmap(0.5 + 0.5 * np.clip(s, -1, 1))
        rgba[..., 3] = np.clip(np.abs(s) * 1.6, 0, 0.85)  # quiet areas transparent
        _png(rgba, os.path.join(out, "frames", "f%03d.png" % i))


def render_pgv(out, grid, pgv):
    """PGV (m/s), log colour scale over 2.5 decades below the peak."""
    g = grid(pgv)
    hi = float(np.nanmax(g))
    lo = hi / 10 ** 2.5
    s = (np.log10(np.clip(np.nan_to_num(g, nan=lo), lo, hi)) - math.log10(lo)) / (
        math.log10(hi) - math.log10(lo))
    rgba = cm.get_cmap("turbo")(s)
    rgba[..., 3] = np.where(np.isnan(g), 0, 0.7)
    _png(rgba, os.path.join(out, "pgv.png"))
    return {"min": lo, "max": hi, "cmap": "turbo", "unit": "m/s", "peak": hi}


def read_seismograms(of_dir, step=5):
    traces = {}
    for path in sorted(glob.glob(os.path.join(of_dir, "*.semv"))):
        net, sta, cha = os.path.basename(path).split(".")[:3]
        d = np.loadtxt(path)
        traces.setdefault("%s.%s" % (net, sta), {})[cha[-1]] = {
            "t0": float(d[0, 0]), "dt": float(d[step, 0] - d[0, 0]),
            "v": [round(float(v), 9) for v in d[::step, 1]],
            "pgv": float(np.abs(d[:, 1]).max()),
        }
    return traces


def postprocess(run_dir, derived, event):
    of_dir = os.path.join(run_dir, "OUTPUT_FILES")
    out = os.path.join(run_dir, "web")
    os.makedirs(out, exist_ok=True)

    movie_files = sorted(glob.glob(os.path.join(of_dir, "moviedata*")))
    if not movie_files:
        raise RuntimeError("no moviedata files in %s" % of_dir)
    x, y, _z, _ux, _uy, uz = _read_records(movie_files[0])
    grid = Grid(x, y, derived["utm_zone"])
    frames = [_read_records(p)[5] for p in movie_files]
    vmax = float(np.percentile(np.abs(np.concatenate(frames)), 99.9)) or 1e-9
    render_frames(out, grid, frames, vmax)

    shake = _read_records(os.path.join(of_dir, "shakingdata"))
    pgv = render_pgv(out, grid, shake[4])

    times = [int(os.path.basename(p)[9:]) * derived["dt"] for p in movie_files]
    stations = {"%s.%s" % (s["network"], s["code"]): s for s in derived["stations"]}
    seis = read_seismograms(of_dir)
    for key, tr in seis.items():
        s = stations.get(key, {})
        tr.update({"latitude": s.get("latitude"), "longitude": s.get("longitude")})

    result = {
        "bounds": grid.bounds,
        "frame_times": [round(t - 1.5 * derived["hdur"], 2) for t in times],
        "frame_count": len(movie_files),
        "velocity_scale": {"vmax": vmax, "compression": "asinh", "unit": "m/s",
                           "cmap": "seismic"},
        "pgv_scale": pgv,
        "seismograms": seis,
        "source": {k: event[k] for k in ("latitude", "longitude", "depth_km", "magnitude",
                                          "strike", "dip", "rake")},
        "half_duration_s": derived["hdur"],
        "dt": derived["dt"], "nstep": derived["nstep"],
    }
    with open(os.path.join(out, "result.json"), "w") as f:
        json.dump(result, f)
    return out, result
