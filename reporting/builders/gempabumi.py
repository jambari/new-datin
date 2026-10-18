"""Laporan Gempabumi: informasi gempabumi yang dianalisis dan disebarkan (Repositori Angkasa)."""
import datetime
import statistics as st
from collections import Counter

from matplotlib.lines import Line2D

from qc_review.models import Event
from reporting.charts import NAVY, new_figure, to_data_uri
from reporting.common import BULAN, fmt
from reporting.osm import ATTRIBUTION, StaticMap

TITLE = "Tersedianya Informasi Gempabumi dan Tsunami yang dianalisis dan disebarkan"
PER_OFFICER = True
WIT = datetime.timezone(datetime.timedelta(hours=9))
STATION = (-2.5145, 140.7043)                     # Stasiun Geofisika Jayapura (JAY)
DEPTH_CLASSES = [("Dangkal (< 70 km)", 0, 70, "#dc2626"), ("Menengah (70–300 km)", 70, 300, "#f59e0b"),
                 ("Dalam (≥ 300 km)", 300, 10_000, "#16a34a")]
MAG_BINS = [("< 3,0", None, 3.0), ("3,0–3,9", 3.0, 4.0), ("4,0–4,9", 4.0, 5.0), ("5,0–5,9", 5.0, 6.0), ("≥ 6,0", 6.0, None)]


def _depth_class(depth):
    for label, lo, hi, color in DEPTH_CLASSES:
        if lo <= (depth or 0) < hi:
            return label, color
    return DEPTH_CLASSES[-1][0], DEPTH_CLASSES[-1][3]


def _mag_bin(mag):
    for label, lo, hi in MAG_BINS:
        if (lo is None or mag >= lo) and (hi is None or mag < hi):
            return label
    return MAG_BINS[0][0]


def _map(events):
    lats = sorted(e["lat"] for e in events)
    lons = sorted(e["lon"] for e in events)
    k = max(1, len(lats) // 100)                    # buang 1% pencilan untuk batas peta
    la0, la1, lo0, lo1 = lats[min(k, len(lats) - 1) if len(lats) > 20 else 0], lats[-k if len(lats) > 20 else -1], \
        lons[min(k, len(lons) - 1) if len(lons) > 20 else 0], lons[-k if len(lons) > 20 else -1]
    la0, la1 = min(la0, STATION[0]), max(la1, STATION[0])
    lo0, lo1 = min(lo0, STATION[1]), max(lo1, STATION[1])
    pad = max(la1 - la0, lo1 - lo0, 1.0) * 0.08
    la0, la1, lo0, lo1 = la0 - pad, la1 + pad, lo0 - pad, lo1 + pad
    span = max(la1 - la0, lo1 - lo0)
    zoom = 8 if span <= 3 else 7 if span <= 6 else 6 if span <= 12 else 5
    smap = StaticMap(la0, la1, lo0, lo1, zoom=zoom)
    fig, ax = new_figure(7.0, 7.0 * smap.height / smap.width)
    ax.imshow(smap.image, extent=(0, smap.width, smap.height, 0))
    ax.grid(False)
    for e in sorted(events, key=lambda e: -(e["depth"] or 0)):
        x, y = smap.project(e["lat"], e["lon"])
        ax.scatter(x, y, s=4 + (max(e["mag"], 1.5) - 1.5) ** 2.2 * 9, c=e["depth_color"], alpha=0.75,
                   edgecolors="#111827", linewidths=0.3)
    sx, sy = smap.project(*STATION)
    ax.plot(sx, sy, marker="^", ms=9, mfc=NAVY, mec="white", mew=1)
    ax.annotate("JAY", (sx, sy), xytext=(6, -12), textcoords="offset points", fontsize=7.5, fontweight="bold",
                bbox=dict(boxstyle="round,pad=.2", fc="white", ec="none", alpha=0.8))
    lon_t = [round(lo0 + (lo1 - lo0) * i / 4, 1) for i in range(5)]
    lat_t = [round(la0 + (la1 - la0) * i / 4, 1) for i in range(5)]
    ax.set_xticks([smap.project(la0, v)[0] for v in lon_t])
    ax.set_xticklabels([f"{v:.1f}°BT" for v in lon_t], fontsize=7)
    ax.set_yticks([smap.project(v, lo0)[1] for v in lat_t])
    ax.set_yticklabels([f"{abs(v):.1f}°{'LS' if v < 0 else 'LU'}" for v in lat_t], fontsize=7)
    ax.set_xlim(0, smap.width)
    ax.set_ylim(smap.height, 0)
    for s in ax.spines.values():
        s.set_visible(True)
    handles = [Line2D([], [], marker="o", ls="", mfc=c, mec="#111827", mew=0.3, ms=6, label=lab)
               for lab, _lo, _hi, c in DEPTH_CLASSES]
    handles += [Line2D([], [], marker="o", ls="", mfc="white", mec="#374151", ms=(4 + (m - 1.5) ** 2.2 * 9) ** 0.5,
                       label=f"M{m:g}".replace(".", ",")) for m in (3, 5)]
    handles.append(Line2D([], [], marker="^", ls="", mfc=NAVY, mec="white", ms=8, label="Stasiun JAY"))
    ax.legend(handles=handles, loc="lower left", fontsize=7, framealpha=0.9, ncol=2)
    ax.text(smap.width - 4, smap.height - 4, ATTRIBUTION, ha="right", va="bottom", fontsize=6.5,
            bbox=dict(fc="white", ec="none", alpha=0.8, pad=1.5))
    ax.set_title("Peta Sebaran Episenter Gempabumi", loc="left")
    return to_data_uri(fig, dpi=150)


def _charts(events, months):
    fig, axs = new_figure(7.4, 2.6, ncols=3, gridspec_kw=dict(width_ratios=[1.3, 1, 1]))
    labels = [BULAN[m][:3] + f" {str(y)[2:]}" for y, m in months]
    counts = Counter((e["time_wit"].year, e["time_wit"].month) for e in events)
    vals = [counts.get(ym, 0) for ym in months]
    axs[0].bar(labels, vals, color=NAVY, width=0.6)
    for i, v in enumerate(vals):
        axs[0].text(i, v + max(vals + [1]) * 0.02, str(v), ha="center", fontsize=7)
    axs[0].set_title("Jumlah per Bulan", loc="left", fontsize=9)
    axs[0].tick_params(axis="x", labelsize=7, rotation=0 if len(labels) <= 4 else 45)
    mags = Counter(_mag_bin(e["mag"]) for e in events)
    axs[1].bar([b[0] for b in MAG_BINS], [mags.get(b[0], 0) for b in MAG_BINS], color="#3b82f6", width=0.6)
    axs[1].set_title("Magnitudo", loc="left", fontsize=9)
    axs[1].tick_params(axis="x", labelsize=6.5, rotation=30)
    deps = Counter(e["depth_class"] for e in events)
    axs[2].bar([d[0].split(" ")[0] for d in DEPTH_CLASSES], [deps.get(d[0], 0) for d in DEPTH_CLASSES],
               color=[d[3] for d in DEPTH_CLASSES], width=0.6)
    axs[2].set_title("Kedalaman", loc="left", fontsize=9)
    axs[2].tick_params(axis="x", labelsize=7)
    fig.tight_layout()
    return to_data_uri(fig)


def build(period, officer=None):
    t0 = datetime.datetime.combine(period.start, datetime.time.min, tzinfo=WIT)
    t1 = datetime.datetime.combine(period.end + datetime.timedelta(days=1), datetime.time.min, tzinfo=WIT)
    qs = (Event.objects.filter(origin_time__gte=t0, origin_time__lt=t1, runs__isnull=False)
          .distinct().prefetch_related("petugas").order_by("origin_time"))
    if officer is not None:
        qs = qs.filter(petugas=officer)
    events = []
    for e in qs:
        if e.magnitude is None:
            continue
        dclass, dcolor = _depth_class(e.depth_km)
        events.append({
            "id": e.public_id, "time_utc": e.origin_time.astimezone(datetime.timezone.utc),
            "time_wit": e.origin_time.astimezone(WIT), "lat": e.latitude, "lon": e.longitude,
            "depth": e.depth_km, "mag": e.magnitude, "mag_type": e.magnitude_type or "M",
            "region": e.region or "", "depth_class": dclass, "depth_color": dcolor,
            "officers": [p.nama for p in e.petugas.all()],
            "officers_short": [p.nama.split(",")[0].strip() for p in e.petugas.all()],
        })
    months = list(period.months)
    monthly = []
    for y, m in months:
        mv = [e for e in events if (e["time_wit"].year, e["time_wit"].month) == (y, m)]
        monthly.append({"label": f"{BULAN[m]} {y}", "n": len(mv),
                        "mag_max": max((e["mag"] for e in mv), default=None),
                        "n_m5": sum(1 for e in mv if e["mag"] >= 5)})
    mags = [e["mag"] for e in events]
    biggest = sorted(events, key=lambda e: -e["mag"])[:5]
    partners = Counter(n for e in events for n in e["officers"] if officer is None or n != officer.nama)
    return {
        "officer": officer, "per_officer": officer is not None,
        "events": events, "n": len(events), "monthly": monthly,
        "mag_min": min(mags, default=None), "mag_max": max(mags, default=None),
        "mag_mean": st.mean(mags) if mags else None,
        "n_m5": sum(1 for m in mags if m >= 5),
        "depth_counts": [(lab, sum(1 for e in events if e["depth_class"] == lab)) for lab, *_ in DEPTH_CLASSES],
        "mag_counts": [(lab, sum(1 for e in events if _mag_bin(e["mag"]) == lab)) for lab, *_ in MAG_BINS],
        "biggest": biggest, "partners": partners.most_common(),
        "map": _map(events) if events else None,
        "chart": _charts(events, months) if events else None,
    }
