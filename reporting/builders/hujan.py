"""Laporan Hujan (penakar OBS & Hellmann) Stasiun Geofisika Jayapura."""
import datetime
import re
import statistics as st
from collections import Counter

from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from hujan.models import Hujan
from reporting.charts import NAVY, new_figure, to_data_uri
from reporting.common import BULAN, fmt

TITLE = "Tersedianya data curah hujan yang berkualitas di Stasiun Geofisika Jayapura"
HELLMANN_OFF = 9999          # penanda alat Hellmann tidak beroperasi pada data stasiun
CATEGORIES = ["Nihil", "Sangat Ringan", "Ringan", "Sedang", "Lebat", "Sangat Lebat", "Tak Terukur"]
CAT_COLORS = {"Nihil": "#e5e7eb", "Sangat Ringan": "#bae6fd", "Ringan": "#60a5fa", "Sedang": "#2563eb",
              "Lebat": "#f59e0b", "Sangat Lebat": "#dc2626", "Tak Terukur": "#9ca3af", "Lainnya": "#d1d5db"}
_TYPO = {"hukan": "hujan", "huan": "hujan", "hujna": "hujan", "sanga t": "sangat", "nihiil": "nihil"}


def normalize_category(raw):
    """Seragamkan penulisan kategori ('Hujan Sangat  Ringan', 'NIHIIL', ...)."""
    text = " ".join((raw or "").lower().split())
    for wrong, right in _TYPO.items():
        text = text.replace(wrong, right)
    text = re.sub(r"^hujan\s+", "", text)
    for cat in sorted(CATEGORIES, key=len, reverse=True):
        if text == cat.lower():
            return cat
    return "" if not text else "Lainnya"


def _hellmann(value):
    return None if value is None or value >= HELLMANN_OFF else value


def _month_chart(label, days):
    fig, ax = new_figure(7.4, 2.7)
    x = [d["date"].day for d in days]
    colors = [CAT_COLORS.get(d["cat"], "#d1d5db") if d["obs"] is not None else "#ffffff" for d in days]
    ax.bar(x, [d["obs"] or 0 for d in days], color=colors, edgecolor=NAVY, linewidth=0.4, width=0.75)
    hx = [d["date"].day for d in days if d["hellmann"] is not None]
    hy = [d["hellmann"] for d in days if d["hellmann"] is not None]
    ax.plot(hx, hy, ls="", marker="o", ms=3.2, mfc="white", mec="#111827", mew=0.9)
    for d in days:
        if d["obs"] is None:
            ax.axvspan(d["date"].day - 0.45, d["date"].day + 0.45, color="#fee2e2", zorder=0)
    ax.set_xlim(0.3, len(days) + 0.7)
    ax.set_xticks(x[::2])
    ax.set_ylabel("Curah hujan (mm)")
    ax.set_xlabel(f"Tanggal ({label})")
    ax.set_ylim(bottom=0)
    used = [c for c in CATEGORIES if any(d["cat"] == c for d in days)]
    handles = [Patch(color=CAT_COLORS[c], label=c) for c in used]
    handles.append(Line2D([], [], ls="", marker="o", mfc="white", mec="#111827", label="Hellmann"))
    if any(d["obs"] is None for d in days):
        handles.append(Patch(color="#fee2e2", label="Tidak ada data"))
    ax.legend(handles=handles, fontsize=6.5, ncol=min(len(handles), 5), frameon=False,
              loc="lower left", bbox_to_anchor=(0, 1.0))
    ax.set_title(f"Curah Hujan Harian (OBS) – {label}", loc="left", pad=26 if len(handles) > 5 else 16)
    return to_data_uri(fig)


def _monthly_totals_chart(months):
    fig, ax = new_figure(7.4, 2.4)
    labels = [m["label"] for m in months]
    totals = [m["total"] for m in months]
    ax.bar(labels, totals, color=NAVY, width=0.55)
    for i, v in enumerate(totals):
        ax.text(i, v + max(totals or [1]) * 0.02, fmt(v, 1), ha="center", fontsize=7.5)
    ax.set_ylabel("Total (mm)")
    ax.set_title("Total Curah Hujan Bulanan (OBS)", loc="left")
    ax.tick_params(axis="x", labelsize=7.5)
    return to_data_uri(fig)


def build(period):
    rows = {h.tanggal: h for h in Hujan.objects.filter(tanggal__range=(period.start, period.end)).order_by("tanggal", "id")}
    raw_labels = set()
    months = []
    all_days = []
    for y, m in period.months:
        start = datetime.date(y, m, 1)
        end = min(period.end, (datetime.date(y + (m == 12), m % 12 + 1, 1) - datetime.timedelta(days=1)))
        days = []
        d = start
        while d <= end:
            h = rows.get(d)
            if h is not None:
                raw_labels.add(h.kategori or "")
            days.append({
                "date": d, "obj": h,
                "obs": h.obs if h else None,
                "hellmann": _hellmann(h.hilman) if h else None,
                "hellmann_off": bool(h and h.hilman is not None and h.hilman >= HELLMANN_OFF),
                "cat": normalize_category(h.kategori) if h else "",
                "note": (h.keterangan or "").strip() if h else "",
                "petugas": h.petugas if h else "",
            })
            d += datetime.timedelta(days=1)
        rec = [x for x in days if x["obs"] is not None]
        total = sum(x["obs"] for x in rec)
        peak = max(rec, key=lambda x: x["obs"]) if rec else None
        label = f"{BULAN[m]} {y}"
        months.append({
            "label": label, "days": days, "n": len(rec), "ndays": len(days),
            "missing": [x["date"] for x in days if x["obs"] is None],
            "total": total, "rainy": sum(1 for x in rec if x["obs"] > 0),
            "peak": peak, "hellmann_off": [x for x in days if x["hellmann_off"]],
            "chart": _month_chart(label, days),
        })
        all_days.extend(days)

    rec = [x for x in all_days if x["obs"] is not None]
    pairs = [x for x in rec if x["hellmann"] is not None]
    diffs = [abs(x["obs"] - x["hellmann"]) for x in pairs]
    big_diff = [x for x in pairs if abs(x["obs"] - x["hellmann"]) > max(1.0, 0.2 * max(x["obs"], x["hellmann"]))]
    cats = Counter(x["cat"] or "(kosong)" for x in rec)
    peak = max(rec, key=lambda x: x["obs"]) if rec else None
    return {
        "months": months, "ndays": period.days, "n_records": len(rec),
        "completeness": 100 * len(rec) / period.days if period.days else None,
        "missing": [x["date"] for x in all_days if x["obs"] is None],
        "total": sum(x["obs"] for x in rec), "rainy": sum(1 for x in rec if x["obs"] > 0),
        "peak": peak,
        "categories": [(c, cats[c]) for c in CATEGORIES + ["Lainnya", "(kosong)"] if cats.get(c)],
        "raw_label_count": len(raw_labels),
        "n_pairs": len(pairs), "mean_abs_diff": st.mean(diffs) if diffs else None,
        "big_diff": big_diff,
        "hellmann_off": [x for x in all_days if x["hellmann_off"]],
        "chart_totals": _monthly_totals_chart(months) if len(months) > 1 else None,
    }
