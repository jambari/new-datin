"""Earthquake H/V response-spectral-ratio site classification (Zhao et al., 2006).

Inputs : spectra/<eventdir>/<ts>_IA_<STA>_<LOC+CHA>_*.psa5  (3 header lines, then "T Sa[g]")
         svel.json  (ShakeMap operational Vs30 sampled at each station)
Output : hv_stations.csv, hv_curves.json

Event metadata comes from the dir name: <ts>_<M*10>_<lat*1000>_<lon*1000>_<...>.
Per record: H = sqrt(Sa_E * Sa_N), HV(T) = H / Sa_Z. Per station: geometric mean
over records passing the filters, then the predominant period T_G = argmax HV
over 0.05-2 s. Zhao et al. (2006, BSSA 96(3)) classes by T_G:
  SC I  <0.2 s (rock, Vs30>600) · SC II 0.2-0.4 (hard soil, 300-600)
  SC III 0.4-0.6 (medium, 200-300) · SC IV >=0.6 (soft, <200)
"""
import csv
import json
import math
import pathlib
import re
import sys
from collections import defaultdict

import numpy as np

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.')
MIN_PGA_G = 2e-4          # ~0.2 gal: drop records too weak to trust
MAX_EPI_KM = 300
MIN_RECORDS = 5
TG_BAND = (0.05, 2.0)

CLASSES = [  # (upper T_G, label, Vs30 range text, representative Vs30)
    (0.2, 'SC I', '>600', 760),
    (0.4, 'SC II', '300-600', 450),
    (0.6, 'SC III', '200-300', 250),
    (math.inf, 'SC IV', '<200', 180),
]


def read_psa5(path):
    rows = []
    for line in path.read_text().split('\n')[3:]:
        parts = line.split()
        if len(parts) == 2:
            rows.append((float(parts[0]), float(parts[1])))
    return np.array(rows)


def epi_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


svel = json.loads((ROOT / 'svel.json').read_text())['stations']
recs = defaultdict(dict)   # (eventdir, station) -> {E/N/Z: array}
for f in (ROOT / 'spectra').glob('*/*.psa5'):
    m = re.match(r'\d{14}_[A-Z0-9]+_([A-Z0-9]+)_([A-Z0-9]+)_', f.name)
    if not m:
        continue
    sta, cha = m.groups()
    comp = cha[-1]
    if comp in 'ENZ':
        recs[(f.parent.name, sta)][comp] = read_psa5(f)

per_station = defaultdict(list)
skipped = defaultdict(int)
T_ref = None
for (evdir, sta), comps in recs.items():
    if set(comps) != {'E', 'N', 'Z'}:
        skipped['missing_component'] += 1
        continue
    parts = evdir.split('_')
    try:
        mag, elat, elon = int(parts[1]) / 10, int(parts[2]) / 1000, int(parts[3]) / 1000
    except (IndexError, ValueError):
        skipped['bad_dirname'] += 1
        continue
    if sta not in svel:
        skipped['unknown_station'] += 1
        continue
    d = epi_km(elat, elon, svel[sta]['lat'], svel[sta]['lon'])
    e, n, z = comps['E'], comps['N'], comps['Z']
    if not (len(e) == len(n) == len(z)) or not np.allclose(e[:, 0], z[:, 0]):
        skipped['period_mismatch'] += 1
        continue
    if d > MAX_EPI_KM:
        skipped['too_far'] += 1
        continue
    pga_h = math.sqrt(e[0, 1] * n[0, 1])
    if pga_h < MIN_PGA_G or np.any(z[:, 1] <= 0) or np.any(e[:, 1] <= 0) or np.any(n[:, 1] <= 0):
        skipped['weak_or_invalid'] += 1
        continue
    T_ref = e[:, 0]
    hv = np.sqrt(e[:, 1] * n[:, 1]) / z[:, 1]
    per_station[sta].append((hv, mag, d, pga_h))

band = (T_ref >= TG_BAND[0]) & (T_ref <= TG_BAND[1])
rows, curves = [], {}
for sta in sorted(svel):
    data = per_station.get(sta, [])
    base = {'station': sta, 'lat': svel[sta]['lat'], 'lon': svel[sta]['lon'],
            'n_records': len(data), 'shakemap_vs30': svel[sta].get('svel_finest')}
    if len(data) < MIN_RECORDS:
        rows.append({**base, 'note': 'too few records'})
        continue
    logs = np.log(np.array([h for h, *_ in data]))
    mean = np.exp(logs.mean(axis=0))
    sd = logs.std(axis=0)
    idx = np.where(band)[0][np.argmax(mean[band])]
    tg, peak = float(T_ref[idx]), float(mean[idx])
    upper, label, vs_range, vs_rep = next(c for c in CLASSES if tg < c[0])
    flat = peak < 2.0
    sm = svel[sta].get('svel_finest')
    sm_class = None
    if sm:
        sm_class = 'SC I' if sm > 600 else 'SC II' if sm > 300 else 'SC III' if sm > 200 else 'SC IV'
    rows.append({**base,
                 'hv_TG_s': round(tg, 3), 'hv_peak': round(peak, 2),
                 'hv_sigma_ln_at_TG': round(float(sd[idx]), 2),
                 'zhao_class': label + (' (flat H/V)' if flat else ''),
                 'zhao_vs30_range': vs_range,
                 'shakemap_class': sm_class,
                 'agrees': (sm_class == label) if sm_class else None,
                 'mag_range': f"{min(m for _, m, _, _ in data):.1f}-{max(m for _, m, _, _ in data):.1f}",
                 'median_epi_km': round(float(np.median([d for *_, d, _ in data])), 0)})
    curves[sta] = {'T': [round(float(t), 4) for t in T_ref], 'hv_mean': [round(float(v), 3) for v in mean],
                   'hv_sigma_ln': [round(float(v), 3) for v in sd], 'n': len(data)}

fields = ['station', 'lat', 'lon', 'n_records', 'mag_range', 'median_epi_km', 'shakemap_vs30',
          'shakemap_class', 'hv_TG_s', 'hv_peak', 'hv_sigma_ln_at_TG', 'zhao_class',
          'zhao_vs30_range', 'agrees', 'note']
with open(ROOT / 'hv_stations.csv', 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader()
    for r in rows:
        w.writerow(r)
(ROOT / 'hv_curves.json').write_text(json.dumps(curves))
print('records used:', sum(len(v) for v in per_station.values()), '| skipped:', dict(skipped))
