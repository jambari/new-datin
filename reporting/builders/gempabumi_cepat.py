"""Laporan kecepatan penyampaian informasi gempabumi M < 5,0 (Repositori Angkasa).

Delta waktu = Event.created_at − waktu kejadian. Sejak 2026 created_at diselaraskan dengan waktu
commit manual pertama petugas di SeisComP (pengiriman ke Repositori Angkasa hanya beberapa detik),
sehingga data impor susulan (Jan–Mei dan Agustus 2026) tetap mencerminkan waktu penyampaian.
Sebelum DELTA_START created_at berasal dari impor susulan dan delta tidak dihitung.
"""
import datetime
import statistics as st
from collections import Counter

from django.db.models import Count, Q

from qc_review.models import Event, StationResult
from qc_review.utils import DELTA_VALID_FROM as DELTA_START
from reporting.builders.gempabumi import _depth_class, _map
from reporting.charts import NAVY, new_figure, to_data_uri
from reporting.common import BULAN
from reporting.seismic_stations import station_health

TITLE = ("Tersedianya informasi gempabumi dengan Magnitudo M < 5.0 "
         "yang disampaikan dalam waktu kurang dari 3 menit")
PER_OFFICER = True
WIT = datetime.timezone(datetime.timedelta(hours=9))
MAG_LIMIT = 5.0
TARGET_MIN = 3.0
GREEN, RED, GREY = "#16a34a", "#dc2626", "#9ca3af"
MAG_CLASSES = [("M < 3,0", 0, 3), ("M 3,0–3,9", 3, 4), ("M 4,0–4,9", 4, 5)]
PICK_CLASSES = [("< 5 stasiun", 0, 5), ("5–7 stasiun", 5, 8), ("8–11 stasiun", 8, 12), ("≥ 12 stasiun", 12, None)]
DELTA_BINS = [("< 1", 0, 1), ("1–2", 1, 2), ("2–3", 2, 3), ("3–5", 3, 5), ("5–10", 5, 10),
              ("10–30", 10, 30), ("≥ 30", 30, None)]


def fmt_delta(seconds):
    s = int(round(seconds))
    h, rem = divmod(abs(s), 3600)
    m, s = divmod(rem, 60)
    out = f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
    return ("-" if seconds < 0 else "") + out


def _pct(a, b):
    return 100.0 * a / b if b else None


def _charts(events, monthly):
    timed = [e for e in events if e["delta_min"] is not None]
    fig, axs = new_figure(7.4, 2.7, ncols=3, gridspec_kw=dict(width_ratios=[1.3, 0.8, 1.3]))
    labels = [m["short"] for m in monthly]
    on = [m["on"] for m in monthly]
    late = [m["late"] for m in monthly]
    axs[0].bar(labels, on, color=GREEN, width=0.6, label="Tepat waktu")
    axs[0].bar(labels, late, bottom=on, color=RED, width=0.6, label="Terlambat")
    for i, m in enumerate(monthly):
        if m["timed"]:
            axs[0].text(i, m["timed"] * 1.02, f"{m['pct_on']:.0f}%".replace(".", ","), ha="center", fontsize=7)
    axs[0].set_title("Per Bulan", loc="left", fontsize=9)
    axs[0].tick_params(axis="x", labelsize=7, rotation=0 if len(labels) <= 4 else 45)
    axs[0].legend(fontsize=6.5, loc="upper left", framealpha=0.9)
    n_on = sum(1 for e in timed if e["on_time"])
    if timed:
        axs[1].pie([n_on, len(timed) - n_on], colors=[GREEN, RED], startangle=90, counterclock=False,
                   autopct=lambda p: f"{p:.1f}%".replace(".", ",") if p else "",
                   textprops=dict(fontsize=7, color="white", fontweight="bold"),
                   wedgeprops=dict(width=0.55, edgecolor="white"), pctdistance=0.72)
    axs[1].set_title("Persentase", loc="left", fontsize=9)
    axs[1].axis("equal")
    bins = Counter(next(lab for lab, lo, hi in DELTA_BINS if e["delta_min"] >= lo and (hi is None or e["delta_min"] < hi))
                   for e in timed if e["delta_min"] >= 0)
    axs[2].bar([b[0] for b in DELTA_BINS], [bins.get(b[0], 0) for b in DELTA_BINS],
               color=[GREEN if (b[2] or 99) <= TARGET_MIN else RED for b in DELTA_BINS], width=0.65)
    axs[2].set_title("Sebaran Delta Waktu (menit)", loc="left", fontsize=9)
    axs[2].tick_params(axis="x", labelsize=7)
    fig.tight_layout()
    return to_data_uri(fig)


def build(period, officer=None):
    t0 = datetime.datetime.combine(period.start, datetime.time.min, tzinfo=WIT)
    t1 = datetime.datetime.combine(period.end + datetime.timedelta(days=1), datetime.time.min, tzinfo=WIT)
    qs = (Event.objects.filter(origin_time__gte=t0, origin_time__lt=t1, runs__isnull=False,
                               magnitude__lt=MAG_LIMIT)
          .distinct().prefetch_related("petugas").order_by("origin_time"))
    if officer is not None:
        qs = qs.filter(petugas=officer)
    qs = list(qs)
    # Jumlah stasiun yang di-pick petugas (fase P) pada commit pertama.
    picks = dict(StationResult.objects.filter(run__event__in=qs, run__run_number=1)
                 .values("run__event_id").annotate(n=Count("id", filter=Q(analyst_p__isnull=False)))
                 .values_list("run__event_id", "n"))
    events = []
    for e in qs:
        dclass, dcolor = _depth_class(e.depth_km)
        delta = None
        if e.origin_time >= DELTA_START and e.created_at:
            delta = (e.created_at - e.origin_time).total_seconds()
        events.append({
            # Tanpa zona (naive) agar filter |date di template tidak mengonversi ke TIME_ZONE server.
            "id": e.public_id, "time_utc": e.origin_time.astimezone(datetime.timezone.utc).replace(tzinfo=None),
            "time_wit": e.origin_time.astimezone(WIT).replace(tzinfo=None),
            "sent_wit": e.created_at.astimezone(WIT).replace(tzinfo=None) if delta is not None else None,
            "lat": e.latitude, "lon": e.longitude, "depth": e.depth_km, "mag": e.magnitude,
            "region": e.region or "", "depth_class": dclass, "depth_color": dcolor, "n_picks": picks.get(e.pk),
            "delta_min": delta / 60 if delta is not None else None,
            "delta_text": fmt_delta(delta) if delta is not None else "–",
            "on_time": delta is not None and delta < TARGET_MIN * 60,
            "officers_short": [p.nama.split(",")[0].strip() for p in e.petugas.all()],
        })
    monthly = []
    for y, m in period.months:
        mv = [e for e in events if (e["time_wit"].year, e["time_wit"].month) == (y, m)]
        timed = [e for e in mv if e["delta_min"] is not None]
        on = sum(1 for e in timed if e["on_time"])
        monthly.append({"label": f"{BULAN[m]} {y}", "short": BULAN[m][:3] + f" {str(y)[2:]}",
                        "n": len(mv), "timed": len(timed), "on": on, "late": len(timed) - on,
                        "pct_on": _pct(on, len(timed)), "pct_late": _pct(len(timed) - on, len(timed)),
                        "median": st.median(e["delta_min"] for e in timed) if timed else None})
    timed = [e for e in events if e["delta_min"] is not None]
    n_on = sum(1 for e in timed if e["on_time"])
    deltas = [e["delta_min"] for e in timed]
    def group(rows, key, classes):
        out = []
        for lab, lo, hi in classes:
            g = [e for e in rows if key(e) is not None and key(e) >= lo and (hi is None or key(e) < hi)]
            on_ = sum(1 for e in g if e["on_time"])
            out.append({"label": lab, "n": len(g), "on": on_, "pct_on": _pct(on_, len(g)),
                        "median": st.median(e["delta_min"] for e in g) if g else None,
                        "picks": st.median(e["n_picks"] for e in g if e["n_picks"] is not None)
                        if any(e["n_picks"] is not None for e in g) else None})
        return out
    health = station_health()
    return {
        "by_mag": group(timed, lambda e: e["mag"], MAG_CLASSES),
        "by_picks": group(timed, lambda e: e["n_picks"], PICK_CLASSES),
        "health": health,
        "map": _map(events, health["stations"] if health else None) if events else None,
        "officer": officer, "per_officer": officer is not None,
        "events": events, "n": len(events), "n_timed": len(timed), "n_untimed": len(events) - len(timed),
        "n_on": n_on, "n_late": len(timed) - n_on,
        "pct_on": _pct(n_on, len(timed)), "pct_late": _pct(len(timed) - n_on, len(timed)),
        "delta_median": st.median(deltas) if deltas else None,
        "delta_min": min(deltas, default=None), "delta_max": max(deltas, default=None),
        "monthly": monthly, "target_min": TARGET_MIN, "mag_limit": MAG_LIMIT,
        "cutoff": DELTA_START.astimezone(WIT).replace(tzinfo=None),
        "chart": _charts(events, monthly) if timed else None,
    }
