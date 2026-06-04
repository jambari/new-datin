"""
Lightning Grid Pipeline: DailyGrid -> MonthlyGrid -> IDW Smoothing.
Grid: 0.5-degree. CG+ and CG- only (no IC).
"""
import django, os, sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "datin_project.settings")
sys.path.insert(0, "/var/www/html")
django.setup()

import numpy as np
from datetime import datetime, timedelta, timezone
from lightning.models import Strike, LightningDailyGrid, LightningMonthlyGrid
from django.db.models import Sum

WIT = timezone(timedelta(hours=9))
GRID = 0.5
LAT_MIN, LAT_MAX = -18.0, 12.0
LON_MIN, LON_MAX = 127.0, 154.0

def build_grid():
    cells = []
    lat = LAT_MIN + GRID/2
    while lat < LAT_MAX:
        lon = LON_MIN + GRID/2
        while lon < LON_MAX:
            cells.append((round(lat, 2), round(lon, 2)))
            lon += GRID
        lat += GRID
    return cells

def compute_daily_grid(grid_date, cells):
    wit_start = datetime(grid_date.year, grid_date.month, grid_date.day, tzinfo=WIT)
    wit_end = wit_start + timedelta(days=1)
    utc_s = wit_start.astimezone(timezone.utc)
    utc_e = wit_end.astimezone(timezone.utc)

    vals = list(Strike.objects.filter(timestamp__gte=utc_s, timestamp__lt=utc_e)
                .values_list("latitude", "longitude", "strike_type"))
    if not vals:
        return []
    lats = np.array([v[0] for v in vals])
    lons = np.array([v[1] for v in vals])
    types = np.array([v[2] for v in vals], dtype=np.int32)

    rows = []
    for lat_c, lon_c in cells:
        mask = ((lats >= lat_c - GRID/2) & (lats < lat_c + GRID/2) &
                (lons >= lon_c - GRID/2) & (lons < lon_c + GRID/2))
        t = types[mask]
        if len(t) == 0:
            continue
        cgp = int(np.sum(t == 0))
        cgm = int(np.sum(t == 1))
        rows.append(LightningDailyGrid(
            grid_date=grid_date, latitude=lat_c, longitude=lon_c,
            cg_plus=cgp, cg_minus=cgm, total=cgp+cgm))
    return rows

def compute_monthly_grid(year, month, cells):
    daily = LightningDailyGrid.objects.filter(grid_date__year=year, grid_date__month=month)
    if not daily.exists():
        return 0
    agg = daily.values("latitude", "longitude").annotate(
        cgp=Sum("cg_plus"), cgm=Sum("cg_minus"), tot=Sum("total"))
    cell_map = {}
    mrows = []
    for r in agg:
        obj = LightningMonthlyGrid(
            year=year, month=month,
            latitude=r["latitude"], longitude=r["longitude"],
            cg_plus=r["cgp"], cg_minus=r["cgm"], total=r["tot"],
            idw_smooth=None)
        mrows.append(obj)
        cell_map[(r["latitude"], r["longitude"])] = obj
    LightningMonthlyGrid.objects.bulk_create(mrows, ignore_conflicts=True)
    _idw_smooth(year, month, cells, cell_map)
    return len(mrows)

def _idw_smooth(year, month, cells, cell_map, power=3.0, radius=3.0):
    pts = [(lat, lon, o.total) for (lat, lon), o in cell_map.items() if o.total > 0]
    if len(pts) < 3:
        return
    coords = np.array([(p[0], p[1]) for p in pts])
    values = np.array([p[2] for p in pts], dtype=np.float64)
    for lat_c, lon_c in cells:
        dx = coords[:, 0] - lat_c
        dy = coords[:, 1] - lon_c
        dists = np.sqrt(dx**2 + dy**2)
        mask = dists <= radius
        if not mask.any():
            continue
        w = 1.0 / (dists[mask] ** power)
        w[~np.isfinite(w)] = 1.0
        sv = float(np.average(values[mask], weights=w))
        LightningMonthlyGrid.objects.update_or_create(
            year=year, month=month,
            latitude=round(lat_c, 2), longitude=round(lon_c, 2),
            defaults={"idw_smooth": round(sv, 1)})

if __name__ == "__main__":
    import sys
    action = sys.argv[1] if len(sys.argv) > 1 else "daily_all"
    cells = build_grid()
    print(f"Grid: {len(cells)} cells of {GRID} deg")

    if action == "daily_all":
        dates = Strike.objects.dates("timestamp", "day", order="ASC")
        print(f"Processing {len(dates)} days...")
        for i, d in enumerate(dates):
            wd = d.astimezone(WIT).date() if hasattr(d, "astimezone") else d
            rows = compute_daily_grid(wd, cells)
            if rows:
                LightningDailyGrid.objects.bulk_create(rows, ignore_conflicts=True, batch_size=500)
            if i % 100 == 0:
                print(f"  [{i}] {wd}: {len(rows)} cells")

    elif action == "monthly_all":
        months = LightningDailyGrid.objects.dates("grid_date", "month", order="ASC")
        for m in months:
            n = compute_monthly_grid(m.year, m.month, cells)
            print(f"  {m.year}-{m.month:02d}: {n} cells")

    elif action == "monthly_one":
        y, m = int(sys.argv[2]), int(sys.argv[3])
        print(f"  {y}-{m:02d}: {compute_monthly_grid(y, m, cells)} cells")

    print(f"Daily: {LightningDailyGrid.objects.count()}  Monthly: {LightningMonthlyGrid.objects.count()}")
