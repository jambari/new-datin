"""Sample ShakeMap's operational Vs30 (grid.xml SVEL) at each station.

Runs on jaygenerator with the shakemap_manager venv (Python 3.6, numpy 1.19).
Reads station coordinates from the Django DB, scans every
crontab_shakemap/.../download/grid.xml, takes the nearest grid node for each
station inside the grid extent, and prints JSON {code: {...}} to stdout.
"""
import glob
import json
import os
import re
import sqlite3
import sys

import numpy as np

DB = os.path.expanduser('~/jaygenerator/shakemap_manager/db.sqlite3')
GRIDS = glob.glob(os.path.expanduser(
    '~/crontab_shakemap/Hasil_ShakemapTerkini/shake/*/download/grid.xml'))

con = sqlite3.connect('file:%s?mode=ro' % DB, uri=True)
stations = {c: (lat, lon) for c, lat, lon in con.execute(
    'select code, latitude, longitude from event_dashboard_station')}

samples = {c: [] for c in stations}
for path in GRIDS:
    with open(path) as fh:
        text = fh.read()
    spec = re.search(r'<grid_specification([^>]*)>', text)
    fields = re.findall(r'<grid_field index="(\d+)" name="(\w+)"', text)
    data = re.search(r'<grid_data>(.*?)</grid_data>', text, re.S)
    if not (spec and fields and data):
        continue
    attrs = dict(re.findall(r'(\w+)="([^"]*)"', spec.group(1)))
    names = [n for _, n in sorted(fields, key=lambda f: int(f[0]))]
    if 'SVEL' not in names:
        continue
    arr = np.array(data.group(1).split(), dtype=float).reshape(-1, len(names))
    lon, lat, svel = arr[:, names.index('LON')], arr[:, names.index('LAT')], arr[:, names.index('SVEL')]
    dx, dy = float(attrs['nominal_lon_spacing']), float(attrs['nominal_lat_spacing'])
    for code, (slat, slon) in stations.items():
        if not (lon.min() <= slon <= lon.max() and lat.min() <= slat <= lat.max()):
            continue
        i = np.argmin((lon - slon) ** 2 + (lat - slat) ** 2)
        if abs(lon[i] - slon) <= dx and abs(lat[i] - slat) <= dy:
            samples[code].append((float(svel[i]), dx))

out = {}
for code, vals in samples.items():
    if not vals:
        out[code] = {'lat': stations[code][0], 'lon': stations[code][1], 'n_grids': 0}
        continue
    v = np.array([s for s, _ in vals])
    finest = min(vals, key=lambda t: t[1])
    out[code] = {
        'lat': stations[code][0], 'lon': stations[code][1], 'n_grids': len(vals),
        'svel_median': round(float(np.median(v)), 1),
        'svel_min': round(float(v.min()), 1), 'svel_max': round(float(v.max()), 1),
        'svel_finest': round(finest[0], 1), 'finest_spacing_deg': finest[1],
    }
json.dump({'n_grid_files': len(GRIDS), 'stations': out}, sys.stdout, indent=1)
