"""Laporan Magnetbumi (absolut + indeks K) dan Listrik Udara (petir)."""
import datetime
import statistics as st
from zoneinfo import ZoneInfo

import matplotlib.dates as mdates
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from hujan.models import Hujan
from lightning.models import DailyStrikeSummary, Strike
from magnet.fmi_kindex import fmi_start_date
from magnet.models import KIndexDaily, MagneticObservation, a_index_criteria
from reporting.charts import NAVY, new_figure, thousands, to_data_uri
from reporting.common import BULAN, fmt
from reporting.osm import ATTRIBUTION, StaticMap

TITLE = "Tersedianya data Magnetbumi dan Listrik Udara yang berkualitas di Papua"
WIT = ZoneInfo("Asia/Jayapura")
C_POS, C_NEG, C_IC, C_RAIN = "#d97706", "#b91c1c", "#9ca3af", "#0284c7"
MAP_MAX_POINTS = 150_000
JAYAPURA = (-2.5333, 140.7167)
# Kotak yang sama dengan ringkasan harian (lightning.tasks): peta menampilkan
# sambaran yang juga dihitung pada statistik.
SUMMARY_BOX = (-3.014833, -2.014833, 140.204667, 141.204667)
MAP_PAD = 0.06
COMPONENTS = [("declination", "Deklinasi D (°)", 4), ("inclination", "Inklinasi I (°)", 4),
              ("total_intensity", "Total intensitas F (nT)", 1), ("horizontal_intensity", "Komponen H (nT)", 1),
              ("vertical_intensity", "Komponen Z (nT)", 1), ("north_component", "Komponen X (nT)", 1),
              ("east_component", "Komponen Y (nT)", 1)]


def _month_bounds(y, m):
    start = datetime.date(y, m, 1)
    end = (datetime.date(y + (m == 12), m % 12 + 1, 1) - datetime.timedelta(days=1))
    return start, end


# --------------------------------------------------------------------- petir
def _petir_month(y, m):
    start, end = _month_bounds(y, m)
    summ = {s.summary_date: s for s in DailyStrikeSummary.objects.filter(summary_date__range=(start, end))}
    rain = {h.tanggal: h.obs for h in Hujan.objects.filter(tanggal__range=(start, end))}
    days = []
    d = start
    while d <= end:
        s = summ.get(d)
        days.append({"date": d, "total": s.total_count if s else 0, "pos": s.cg_plus_count if s else 0,
                     "neg": s.cg_minus_count if s else 0, "ic": s.ic_count if s else 0,
                     "has_summary": s is not None, "rain": rain.get(d)})
        d += datetime.timedelta(days=1)
    total = sum(x["total"] for x in days)
    peak = max(days, key=lambda x: x["total"])
    return {
        "label": f"{BULAN[m]} {y}", "days": days, "total": total,
        "pos": sum(x["pos"] for x in days), "neg": sum(x["neg"] for x in days), "ic": sum(x["ic"] for x in days),
        "mean": total / len(days), "peak": peak, "active": sum(1 for x in days if x["total"] > 0),
        "zero": [x["date"] for x in days if x["total"] == 0],
        "zero_rain": [x["date"] for x in days if x["total"] == 0 and (x["rain"] or 0) > 0],
        "no_summary": [x["date"] for x in days if not x["has_summary"]],
        "rain": sum(x["rain"] or 0 for x in days), "ndays": len(days),
    }


def _petir_chart(month):
    days = month["days"]
    x = [d["date"].day for d in days]
    fig, ax = new_figure(7.4, 2.8)
    neg = [d["neg"] for d in days]
    pos = [d["pos"] for d in days]
    ic = [d["ic"] for d in days]
    ax.bar(x, neg, color=C_NEG, width=0.75, label="CG− (negatif)")
    ax.bar(x, pos, bottom=neg, color=C_POS, width=0.75, label="CG+ (positif)")
    ax.bar(x, ic, bottom=[a + b for a, b in zip(neg, pos)], color=C_IC, width=0.75, label="IC (awan)")
    ax.set_xlim(0.3, len(x) + 0.7)
    ax.set_xticks(x[::2])
    ax.set_xlabel(f"Tanggal ({month['label']}, WIT)")
    ax.set_ylabel("Jumlah sambaran")
    thousands(ax)
    a2 = ax.twinx()
    a2.plot(x, [d["rain"] or 0 for d in days], color=C_RAIN, marker="o", ms=2.5, lw=1.1, label="Curah hujan (mm)")
    a2.set_ylabel("Curah hujan (mm)", color=C_RAIN)
    a2.grid(False)
    a2.spines["right"].set_visible(True)
    a2.set_ylim(bottom=0)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = a2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="lower right", fontsize=7, frameon=False, ncol=4, bbox_to_anchor=(1, 1.0))
    ax.set_title(f"Sambaran Petir Harian – {month['label']}", loc="left", pad=16)
    return to_data_uri(fig)


def _strikes(y, m):
    """Titik sambaran unik (tabel Strike bisa berisi duplikat) di dalam kotak ringkasan."""
    start, end = _month_bounds(y, m)
    t0 = datetime.datetime.combine(start, datetime.time.min, tzinfo=WIT)
    t1 = datetime.datetime.combine(end + datetime.timedelta(days=1), datetime.time.min, tzinfo=WIT)
    lat0, lat1, lon0, lon1 = SUMMARY_BOX
    qs = (Strike.objects.filter(timestamp__gte=t0, timestamp__lt=t1, latitude__range=(lat0, lat1),
                                longitude__range=(lon0, lon1))
          .values_list("epoch_ms", "latitude", "longitude", "strike_type").distinct())
    rows = list(qs)
    step = max(1, -(-len(rows) // MAP_MAX_POINTS))
    return len(rows), [(la, lo, t) for _e, la, lo, t in rows[::step]], step


def _map(month_label, pts, n_total, step, bbox):
    lat0, lat1, lon0, lon1 = bbox
    span = max(lat1 - lat0, lon1 - lon0)
    zoom = 10 if span <= 1.5 else 9 if span <= 3 else 8 if span <= 6 else 7
    smap = StaticMap(lat0, lat1, lon0, lon1, zoom=zoom)
    fig, ax = new_figure(7.0, 7.0 * smap.height / smap.width)
    ax.imshow(smap.image, extent=(0, smap.width, smap.height, 0))
    ax.grid(False)
    counts = {}
    for t, color, size in ((2, C_IC, 0.8), (1, C_NEG, 1.1), (0, C_POS, 1.1)):
        sel = [smap.project(la, lo) for la, lo, st_ in pts if (st_ if st_ in (0, 1) else 2) == t]
        counts[t] = len(sel)
        if sel:
            xs, ys = zip(*sel)
            ax.scatter(xs, ys, s=size, c=color, alpha=0.45, linewidths=0)
    jx, jy = smap.project(*JAYAPURA)
    ax.plot(jx, jy, marker="^", ms=7, mec="k", mfc=NAVY)
    ax.annotate("Kota Jayapura", (jx, jy), xytext=(6, -10), textcoords="offset points", fontsize=7.5,
                fontweight="bold", bbox=dict(boxstyle="round,pad=.2", fc="white", ec="none", alpha=0.75))
    lon_ticks = [round(lon0 + (lon1 - lon0) * k / 4, 2) for k in range(5)]
    lat_ticks = [round(lat0 + (lat1 - lat0) * k / 4, 2) for k in range(5)]
    ax.set_xticks([smap.project(lat0, lo)[0] for lo in lon_ticks])
    ax.set_xticklabels([f"{lo:.2f}°BT" for lo in lon_ticks], fontsize=7)
    ax.set_yticks([smap.project(la, lon0)[1] for la in lat_ticks])
    ax.set_yticklabels([f"{abs(la):.2f}°{'LS' if la < 0 else 'LU'}" for la in lat_ticks], fontsize=7)
    ax.set_xlim(0, smap.width)
    ax.set_ylim(smap.height, 0)
    for s in ax.spines.values():
        s.set_visible(True)
    handles = [Line2D([], [], marker="o", ls="", mfc=c, mec=c, ms=5, label=f"{lab} ({fmt(counts.get(t, 0) * step, 0)})")
               for t, c, lab in ((0, C_POS, "CG+"), (1, C_NEG, "CG−"), (2, C_IC, "IC/lainnya")) if counts.get(t)]
    ax.legend(handles=handles, loc="lower left", fontsize=7.5, framealpha=0.9)
    ax.text(smap.width - 4, smap.height - 4, ATTRIBUTION, ha="right", va="bottom", fontsize=6.5,
            bbox=dict(fc="white", ec="none", alpha=0.8, pad=1.5))
    ax.set_title(f"Peta Sebaran Sambaran Petir – {month_label}", loc="left")
    return to_data_uri(fig, dpi=150)


# ---------------------------------------------------------------- magnet abs
def _magnet(period):
    qs = list(MagneticObservation.objects.filter(observation_date__range=(period.start, period.end))
              .order_by("observation_date", "session", "id"))
    reduced = [o for o in qs if o.declination is not None]
    dim_raw = []
    for o in qs:
        readings = o.deklinasi_readings or {}
        if o.declination is None and any(isinstance(v, dict) and "circ" in v for v in readings.values()):
            ft = [float(v.get("ftotal")) for v in (o.inklinasi_readings or {}).values()
                  if isinstance(v, dict) and v.get("ftotal") not in (None, "")]
            times = sorted(f"{int(v.get('hh', 0)):02d}:{int(v.get('mm', 0)):02d}" for v in readings.values()
                           if isinstance(v, dict) and "hh" in v)
            dim_raw.append({"obj": o, "f": sum(ft) / len(ft) if len(ft) == 4 else None,
                            "window": f"{times[0]}–{times[-1]}" if times else "", "reduced": False})
    mislabel = []
    for r in reduced:
        for d in dim_raw:
            if (d["obj"].observation_date == r.observation_date and d["f"] is not None and r.total_intensity
                    and abs(d["f"] - float(r.total_intensity)) < 0.05):
                d["reduced"] = True
                if d["obj"].session != r.session:
                    mislabel.append((r.observation_date, r.session, d["obj"].session))
    return reduced, dim_raw, mislabel


def _magnet_chart(month_label, rows, ndays):
    fig, axs = new_figure(7.4, 7.2, nrows=4, ncols=2)
    axs = axs.ravel()
    for i, (field, label, digits) in enumerate(COMPONENTS):
        ax = axs[i]
        if rows:
            xs = [o.observation_date.day + (0.25 if o.session.strip().endswith("2") else 0) for o in rows]
            ys = [float(getattr(o, field)) for o in rows]
            ax.plot(xs, ys, color=NAVY, lw=1, marker="o", ms=4, mfc="white", mew=1.3)
            for xx, yy in zip(xs, ys):
                ax.annotate(fmt(yy, digits), (xx, yy), xytext=(0, 5), textcoords="offset points", fontsize=5.6, ha="center")
            pad = (max(ys) - min(ys)) * 0.35 or abs(ys[0]) * 1e-3 + 0.01
            ax.set_ylim(min(ys) - pad, max(ys) + pad * 1.6)
        else:
            ax.text(0.5, 0.5, "Tidak ada observasi", ha="center", va="center", transform=ax.transAxes, color="#9ca3af")
        ax.set_xlim(0.5, ndays + 0.5)
        ax.set_xticks(range(1, ndays + 1, 3))
        ax.set_title(label, loc="left", fontsize=8.5)
        ax.tick_params(labelsize=7)
        ax.ticklabel_format(axis="y", useOffset=False, style="plain")
    axs[-1].axis("off")
    axs[-1].text(0, 0.7, f"Observasi absolut geomagnet\nStasiun Jayapura (JYP)\n{month_label}\n\n"
                 f"Sesi tereduksi: {len(rows)}\nSumbu x: tanggal", fontsize=8, va="top", color="#374151")
    fig.suptitle(f"Nilai Absolut Magnetbumi – {month_label}", x=0.02, ha="left", fontweight="bold", fontsize=10.5)
    fig.tight_layout()
    return to_data_uri(fig, dpi=140)


# ------------------------------------------------------------------- K index
def _kcolor(k):
    return ("#22c55e" if k <= 3 else "#eab308" if k == 4 else "#f97316" if k <= 6
            else "#dc2626" if k == 7 else "#c026d3" if k == 8 else "#6b21a8")


def _kindex_month(y, m):
    start, end = _month_bounds(y, m)
    rows = {r.tanggal: r for r in KIndexDaily.objects.filter(tanggal__range=(start, end))}
    days = []
    d = start
    while d <= end:
        days.append({"date": d, "obj": rows.get(d)})
        d += datetime.timedelta(days=1)
    with_data = [x["obj"] for x in days if x["obj"] and x["obj"].has_data]
    crit = {}
    for o in with_data:
        crit[o.criteria] = crit.get(o.criteria, 0) + 1
    return {
        "label": f"{BULAN[m]} {y}", "days": days, "n": len(with_data), "ndays": len(days),
        "missing": [x["date"].day for x in days if not (x["obj"] and x["obj"].has_data)],
        "partial": [x["date"].day for x in days if x["obj"] and x["obj"].has_data and not x["obj"].is_complete],
        "sources": sorted({o.get_sumber_display() for o in with_data}),
        "kmax": max((o.k_max for o in with_data), default=None),
        "kmax_days": [o.tanggal.day for o in with_data if o.k_max == max(p.k_max for p in with_data)] if with_data else [],
        "amean": st.mean(o.a_index for o in with_data) if with_data else None,
        "amax": max(with_data, key=lambda o: o.a_index) if with_data else None,
        "criteria": crit,
        "a_diff": [o for o in with_data if o.a_index_source is not None and abs(o.a_index - o.a_index_source) > 0.01],
    }


def _kindex_chart(month):
    days = month["days"]
    nd = len(days)
    fig, (ax, a2) = new_figure(7.4, 4.2, nrows=2, sharex=True, gridspec_kw=dict(height_ratios=[2.2, 1]))
    for x in days:
        o, day = x["obj"], x["date"].day
        if not (o and o.has_data):
            ax.axvspan(day - 1, day, color="#f3f4f6", zorder=0)
            continue
        for j, k in enumerate(o.k_values):
            if k is None:
                ax.axvspan(day - 1 + j / 8, day - 1 + (j + 1) / 8, color="#f3f4f6", zorder=0)
                continue
            ax.bar(day - 1 + j / 8 + 1 / 16, k, width=1 / 8, color=_kcolor(k), edgecolor="white", linewidth=0.15)
        a2.bar(day - 0.5, o.a_index, width=0.7,
               color=NAVY if o.a_index < 30 else "#f97316" if o.a_index < 50 else "#dc2626")
    ax.set_ylim(0, 9)
    ax.set_yticks(range(10))
    ax.set_ylabel("Indeks K (3 jam)")
    ax.legend(handles=[Patch(color=c, label=lab) for c, lab in (("#22c55e", "K 0–3"), ("#eab308", "K 4"),
              ("#f97316", "K 5–6"), ("#dc2626", "K 7"), ("#c026d3", "K 8"), ("#6b21a8", "K 9"),
              ("#f3f4f6", "Tidak ada data"))], fontsize=6.5, ncol=7, frameon=False, loc="lower left", bbox_to_anchor=(0, 1.0))
    ax.set_title(f"Indeks K Stasiun Jayapura per 3 Jam – {month['label']}", loc="left", pad=18)
    a2.axhline(30, color="#f97316", lw=0.8, ls="--")
    a2.set_ylabel("Indeks A")
    a2.set_xlim(0, nd)
    a2.set_xticks([i - 0.5 for i in range(1, nd + 1)])
    a2.set_xticklabels(range(1, nd + 1), fontsize=6.3)
    a2.set_xlabel(f"Tanggal ({month['label']}, UTC)")
    return to_data_uri(fig, dpi=150)


def kindex_report(period):
    """Bagian indeks K/A: dipakai laporan SKP ini dan halaman Lapbul Magnet."""
    kmonths = [_kindex_month(y, m) for y, m in period.months]
    for k in kmonths:
        k["chart"] = _kindex_chart(k) if k["n"] else None
    kdays = sum(k["n"] for k in kmonths)
    storms = sorted((o for k in kmonths for o in (x["obj"] for x in k["days"]) if o and o.has_data and o.a_index >= 30),
                    key=lambda o: o.tanggal)
    return {
        "kmonths": kmonths, "kdays": kdays, "kdays_pct": 100 * kdays / period.days,
        "k_storms": [(o, a_index_criteria(o.a_index)) for o in storms],
        "k_diffs": [o for k in kmonths for o in k["a_diff"]],
        "k_fmi_start": fmi_start_date(),
    }


# --------------------------------------------------------------------- build
def build(period, include_maps=True):
    petir = [_petir_month(y, m) for y, m in period.months]
    lat0, lat1, lon0, lon1 = SUMMARY_BOX
    bbox = (lat0 - MAP_PAD, lat1 + MAP_PAD, lon0 - MAP_PAD, lon1 + MAP_PAD)
    for (y, m), month in zip(period.months, petir):
        month["chart"] = _petir_chart(month)
        n, pts, step = _strikes(y, m) if include_maps else (0, [], 1)
        month["map_points"] = n
        month["map_mismatch"] = bool(include_maps and month["total"]
                                     and abs(n - month["total"]) > 0.05 * month["total"])
        month["map"] = _map(month["label"], pts, n, step, bbox) if pts else None

    reduced, dim_raw, mislabel = _magnet(period)
    magnet_months = []
    for y, m in period.months:
        rows = [o for o in reduced if (o.observation_date.year, o.observation_date.month) == (y, m)]
        dims = [d for d in dim_raw if (d["obj"].observation_date.year, d["obj"].observation_date.month) == (y, m)]
        _s, e = _month_bounds(y, m)
        magnet_months.append({"label": f"{BULAN[m]} {y}", "reduced": rows, "dim": dims,
                              "chart": _magnet_chart(f"{BULAN[m]} {y}", rows, e.day)})
    ranges = {}
    for field, label, digits in COMPONENTS:
        vals = [float(getattr(o, field)) for o in reduced if getattr(o, field) is not None]
        ranges[field] = (max(vals) - min(vals)) if len(vals) > 1 else None

    total = sum(p["total"] for p in petir)
    return {
        "petir": petir, "petir_total": total,
        "petir_pos": sum(p["pos"] for p in petir), "petir_neg": sum(p["neg"] for p in petir),
        "petir_ic": sum(p["ic"] for p in petir), "petir_active": sum(p["active"] for p in petir),
        "petir_zero": sum(len(p["zero"]) for p in petir), "petir_rain": sum(p["rain"] for p in petir),
        "petir_map_points": sum(p["map_points"] for p in petir), "ndays": period.days,
        "magnet_reduced": reduced, "magnet_dim": dim_raw, "magnet_mislabel": mislabel,
        "magnet_months": magnet_months, "magnet_ranges": ranges,
        "magnet_sessions": len(reduced) + sum(1 for d in dim_raw if not d["reduced"]),
        "magnet_empty_months": [mm["label"] for mm in magnet_months if not mm["reduced"] and not mm["dim"]],
        **kindex_report(period),
    }
