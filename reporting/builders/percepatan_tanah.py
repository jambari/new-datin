"""Laporan Percepatan Tanah (spektrum respons .psa5 dari ShakeMap)."""
import datetime
import math
from collections import defaultdict

from repository.models import EventResponseSpectrum, FeltEarthquake, Station
from repository.shakemap_lookup import candidate_ids, shakemap_index, wib_id_to_utc
from reporting.charts import new_figure, to_data_uri

TITLE = "Tersedianya data percepatan tanah yang berkualitas di Papua"
NEAREST_STATIONS = 3
PERIODS = (("sa03", 0.3), ("sa10", 1.0), ("sa30", 3.0))


def _parse_event_time(event_id):
    """Waktu UTC dari id .psa5 (stempel waktu WIB 14 digit)."""
    return wib_id_to_utc(event_id)


def _event_meta(event_id, t, index, felt):
    """(ShakemapEvent atau None, dict metadata). Metadata dari ShakemapEvent bila lengkap,
    selain itu dari gempa dirasakan BMKG (±10 detik): record yang dibuat otomatis saat push
    berisi magnitudo/koordinat 0."""
    sm = next((index[c] for c in candidate_ids(event_id[:14]) if c in index), None)
    if sm and sm.magnitude and (sm.latitude or sm.longitude):
        return sm, {"mag": sm.magnitude, "depth": sm.depth, "lat": sm.latitude, "lon": sm.longitude,
                    "location": sm.location_string}
    fe = min((f for f in felt if abs((f.event_datetime - t).total_seconds()) <= 10),
             key=lambda f: abs((f.event_datetime - t).total_seconds()), default=None)
    if fe:
        return sm, {"mag": fe.magnitude, "depth": fe.depth_km, "lat": fe.latitude, "lon": fe.longitude,
                    "location": fe.wilayah}
    return sm, {"mag": None, "depth": None, "lat": None, "lon": None, "location": ""}


def _sa_at(points, period):
    """Sa pada periode T (interpolasi linear)."""
    pts = sorted((p["T"], p["Sa"]) for p in points if p.get("T") is not None and p.get("Sa") is not None)
    for (t0, s0), (t1, s1) in zip(pts, pts[1:]):
        if t0 <= period <= t1:
            return s0 if t1 == t0 else s0 + (s1 - s0) * (period - t0) / (t1 - t0)
    return None


def _haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def _qc(rec):
    vals = [rec["pga"], rec["sa03"], rec["sa10"], rec["sa30"], rec["peak"]]
    if any(v is None for v in vals):
        return "data tidak lengkap"
    if max(vals) > 3:
        return "nilai > 3 g (di luar rentang fisis)"
    if min(rec["pga"], rec["sa03"], rec["sa10"]) <= 0:
        return "nilai nol"
    if rec["pga"] < 0.1 * rec["sa10"]:
        return "PGA tidak konsisten dengan Sa(1,0 s)"
    if rec["sa03"] < 0.05 * rec["pga"]:
        return "spike (Sa 0,3 s << PGA)"
    return None


def _pga_distance_chart(records):
    ok = [r for r in records if not r["qc"] and r["dist"] is not None and r["horizontal"]]
    if not ok:
        return None
    fig, ax = new_figure(7.4, 3.0)
    sc = ax.scatter([r["dist"] for r in ok], [r["pga"] for r in ok], c=[r["mag"] or 0 for r in ok],
                    cmap="viridis", s=14, edgecolors="none")
    ax.set_yscale("log")
    ax.set_xlabel("Jarak episenter (km)")
    ax.set_ylabel("PGA horizontal (g)")
    ax.set_title("PGA terhadap Jarak (rekaman lolos QC, komponen horizontal)", loc="left")
    cb = fig.colorbar(sc, ax=ax, pad=0.01)
    cb.set_label("Magnitudo")
    return to_data_uri(fig)


def build(period):
    t0 = datetime.datetime.combine(period.start, datetime.time.min, tzinfo=datetime.timezone.utc)
    t1 = datetime.datetime.combine(period.end, datetime.time.max, tzinfo=datetime.timezone.utc)
    # id WIB = UTC + 7 jam: kejadian akhir bulan (UTC) bisa ber-id bulan berikutnya.
    months = list(period.months)
    nxt = (months[-1][0] + (months[-1][1] == 12), months[-1][1] % 12 + 1)
    prefixes = {f"{y}{m:02d}" for y, m in months + [nxt]}
    spectra = defaultdict(list)
    for ers in EventResponseSpectrum.objects.filter(event_id__regex=r"^(%s)" % "|".join(sorted(prefixes))):
        t = _parse_event_time(ers.event_id)
        if t and t0 <= t <= t1:
            spectra[ers.event_id].append(ers)

    index = shakemap_index()
    felt = list(FeltEarthquake.objects.filter(event_datetime__range=(t0 - datetime.timedelta(minutes=1),
                                                                      t1 + datetime.timedelta(minutes=1))))
    codes = {e.station_code for lst in spectra.values() for e in lst}
    stations = {s.code: s for s in Station.objects.filter(code__in=codes)}

    events, all_records = [], []
    for event_id in sorted(spectra):
        sm, meta = _event_meta(event_id, _parse_event_time(event_id), index, felt)
        by_station = defaultdict(list)
        for ers in spectra[event_id]:
            by_station[ers.station_code].append(ers)
        dist = {}
        for code in by_station:
            st = stations.get(code)
            dist[code] = (_haversine_km(meta["lat"], meta["lon"], st.latitude, st.longitude)
                          if meta["lat"] is not None and st else None)
        chosen = sorted(by_station, key=lambda c: (dist[c] is None, dist[c] or 0))[:NEAREST_STATIONS]
        records = []
        for code in chosen:
            for ers in sorted(by_station[code], key=lambda e: e.component):
                pts = ers.spectrum or []
                rec = {"station": code, "station_name": getattr(stations.get(code), "name", "") or "",
                       "dist": dist[code], "component": ers.component,
                       "horizontal": ers.component[-1:] in ("E", "N", "1", "2"),
                       "pga": _sa_at(pts, 0.0) if pts and pts[0].get("T") == 0 else None,
                       "peak": max((p["Sa"] for p in pts if p.get("Sa") is not None), default=None),
                       "mag": meta["mag"]}
                if rec["pga"] is None and pts:
                    rec["pga"] = min(pts, key=lambda p: p.get("T", 9))["Sa"]
                for key, period_s in PERIODS:
                    rec[key] = _sa_at(pts, period_s)
                rec["qc"] = _qc(rec)
                records.append(rec)
        bad = {r["station"] for r in records if r["qc"]}
        for r in records:
            if not r["qc"] and r["station"] in bad:
                r["qc"] = "komponen lain di stasiun ini anomali"
        valid_h = [r for r in records if not r["qc"] and r["horizontal"]]

        def best(key):
            return max(valid_h, key=lambda r: r[key]) if valid_h else None

        events.append({
            "event_id": event_id, "time": _parse_event_time(event_id), "shakemap": sm,
            "mag": meta["mag"], "depth": meta["depth"], "location": meta["location"],
            "has_meta": meta["mag"] is not None,
            "image": sm.shakemap_image if sm and sm.shakemap_image else None,
            "records": records, "nearest": records[0] if records else None,
            "pga": best("pga"), "sa03": best("sa03"), "sa10": best("sa10"), "sa30": best("sa30"),
            "n_stations": len(by_station),
        })
        all_records.extend(records)

    bad = [r for r in all_records if r["qc"]]
    reasons, bad_stations = defaultdict(int), defaultdict(int)
    for r in bad:
        reasons[r["qc"]] += 1
        bad_stations[r["station"]] += 1
    with_values = [e for e in events if e["pga"]]
    top_pga = max(with_values, key=lambda e: e["pga"]["pga"]) if with_values else None
    top_sa = max(with_values, key=lambda e: e["sa03"]["sa03"]) if with_values else None
    months = defaultdict(int)
    for e in events:
        months[(e["time"].year, e["time"].month)] += 1
    mags = [e["mag"] for e in events if e["mag"] is not None]
    return {
        "events": events, "n_events": len(events), "n_records": len(all_records),
        "n_ok": len(all_records) - len(bad), "n_bad": len(bad),
        "ok_pct": 100 * (len(all_records) - len(bad)) / len(all_records) if all_records else None,
        "reasons": sorted(reasons.items(), key=lambda x: -x[1]),
        "bad_stations": sorted(bad_stations.items(), key=lambda x: -x[1]),
        "n_stations": len({r["station"] for r in all_records}),
        "events_valid": len(with_values),
        "events_without_shakemap": sum(1 for e in events if not e["has_meta"]),
        "events_without_image": sum(1 for e in events if not e["image"]),
        "top_pga": top_pga, "top_sa": top_sa,
        "mag_min": min(mags, default=None), "mag_max": max(mags, default=None),
        "per_month": [(y, m, months.get((y, m), 0)) for y, m in period.months],
        "nearest_n": NEAREST_STATIONS,
        "chart_pga": _pga_distance_chart(all_records),
    }
