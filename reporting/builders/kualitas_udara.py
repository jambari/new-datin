"""Laporan Kualitas Udara (KAH & SPM)."""
import datetime
import statistics as st

from matplotlib.patches import Patch

from kualitas_udara.models import KAH_PARAM_INFO, SPM_THRESHOLD, KAHSeriesData, SPMSeriesData
from reporting.charts import GREEN, NAVY, RED, new_figure, to_data_uri
from reporting.common import BULAN, fmt

TITLE = "Tersedianya data Kualitas Udara yang berkualitas di Stasiun Geofisika Jayapura"
ION_FIELDS = ("ph", "dh", "ca", "mg", "na", "k", "nh4", "cl", "so4", "no3")
IONS = [("so4", r"SO$_4^{2-}$", "#7c3aed"), ("no3", r"NO$_3^{-}$", "#a78bfa"), ("cl", r"Cl$^{-}$", "#0ea5e9"),
        ("na", r"Na$^{+}$", "#38bdf8"), ("ca", r"Ca$^{2+}$", "#f59e0b"), ("mg", r"Mg$^{2+}$", "#fbbf24"),
        ("k", r"K$^{+}$", "#84cc16"), ("nh4", r"NH$_4^{+}$", "#14b8a6")]
SPM_INTERVAL_DAYS = 6


def h_plus(ph):
    """Konsentrasi H+ (µeq/L) dari pH."""
    return 10 ** (-ph) * 1e6


def _label(rec):
    return f"{BULAN[int(rec.bulan[5:])][:3]} {rec.bulan[2:4]} M{int(rec.minggu)}"


def _qc(records):
    valid = [r for r in records if not r.is_empty]
    med = {k: st.median(getattr(r, k) or 0 for r in valid) for k in ("dh", "mg")} if valid else {}
    for r in records:
        if r.is_empty:
            r.qc = "Tidak ada sampel"
        elif r.ph is None or not 3 <= r.ph <= 9:
            r.qc = "pH di luar rentang fisis"
        elif (r.dh or 0) > 5 * med["dh"] or (r.mg or 0) > 5 * med["mg"]:
            r.qc = "Perlu verifikasi (DHL/Mg ekstrem)"
        else:
            r.qc = "Lolos QC"
        r.ac_inconsistent = (not r.is_empty and r.ph and r.ac == 0 and h_plus(r.ph) > 5)
        r.h_plus = h_plus(r.ph) if r.ph else None
        r.ca_mg = (r.ca or 0) + (r.mg or 0)
    return med


def _ph_chart(records):
    fig, ax = new_figure(7.4, 3.0)
    for i, r in enumerate(records):
        if r.is_empty:
            ax.bar(i, 7.6, color="#f3f4f6", width=0.8, zorder=0)
            continue
        ver = r.qc.startswith("Perlu")
        color = "#9ca3af" if ver else (RED if r.ph < 5.6 else GREEN)
        ax.bar(i, r.ph, color=color, width=0.62, hatch="///" if ver else None,
               edgecolor="#6b7280" if ver else "white", lw=0.6)
        ax.text(i, r.ph + 0.1, fmt(r.ph), ha="center", fontsize=6.3)
    ax.axhline(5.6, color=RED, ls="--", lw=1)
    ax.text(-0.45, 5.72, "batas hujan asam pH 5,6", fontsize=7, color=RED)
    ax.set_xticks(range(len(records)))
    ax.set_xticklabels([_label(r) for r in records], rotation=60, ha="right", fontsize=6.3)
    ax.set_ylim(0, 8)
    ax.set_xlim(-0.6, max(len(records), 1) - 0.4)
    ax.set_ylabel("pH")
    ax.legend(handles=[Patch(color=RED, label="pH < 5,6 (asam)"), Patch(color=GREEN, label="pH ≥ 5,6"),
                       Patch(facecolor="#9ca3af", hatch="///", edgecolor="#6b7280", label="perlu verifikasi"),
                       Patch(color="#f3f4f6", label="tidak ada sampel")],
              fontsize=6.5, ncol=4, frameon=False, loc="lower left", bbox_to_anchor=(0, 1.0))
    ax.set_title("pH Air Hujan Mingguan", loc="left", pad=18)
    return to_data_uri(fig)


def _ion_chart(records):
    fig, (ax, a2) = new_figure(7.4, 4.4, nrows=2, sharex=True, gridspec_kw=dict(height_ratios=[1.7, 1]))
    cap = 8
    for i, r in enumerate(records):
        if r.is_empty:
            continue
        bottom = 0
        for key, _label_, color in IONS:
            v = getattr(r, key) or 0
            ax.bar(i, v, bottom=bottom, color=color, width=0.62)
            bottom += v
        if bottom > cap:
            ax.text(i, cap * 0.97, f"total\n{fmt(bottom, 1)} ↑", ha="center", va="top", fontsize=6, fontweight="bold")
        a2.bar(i, r.dh or 0, color=NAVY, width=0.62)
        a2.text(i, min(r.dh or 0, 60) + 1.5, fmt(r.dh, 1), ha="center", fontsize=6)
    ax.set_ylim(0, cap)
    ax.set_ylabel("Ion (mg/L)")
    ax.legend(handles=[Patch(color=c, label=lab) for _k, lab, c in IONS], fontsize=6.5, ncol=8,
              frameon=False, loc="lower left", bbox_to_anchor=(0, 1.0))
    ax.set_title("Komposisi Ion Utama dan DHL per Sampel", loc="left", pad=18)
    a2.set_ylim(0, 70)
    a2.set_ylabel("DHL (µS/cm)")
    a2.set_xticks(range(len(records)))
    a2.set_xticklabels([_label(r) for r in records], rotation=60, ha="right", fontsize=6.3)
    a2.set_xlim(-0.6, max(len(records), 1) - 0.4)
    return to_data_uri(fig)


def _spm_chart(spm):
    import matplotlib.dates as mdates

    t = [r.timestamp for r in spm]
    v = [r.spm for r in spm]
    fig, (ax, a2) = new_figure(7.4, 2.8, ncols=2, gridspec_kw=dict(width_ratios=[2.3, 1]))
    ax.plot(t, v, color=NAVY, marker="o", ms=3.5, lw=1.2)
    if len(spm) <= 40:
        for a, b in zip(t, v):
            ax.annotate(fmt(b, 1), (a, b), xytext=(0, 5), textcoords="offset points", ha="center", fontsize=6)
    ax.set_ylim(0, max(v) * 1.3)
    ax.set_ylabel("SPM (µg/m³)")
    ax.set_title("Konsentrasi SPM per Sampel (24 jam)", loc="left")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m/%y"))
    ax.tick_params(axis="x", labelsize=6.5, rotation=30)
    vals = [st.mean(v), max(v), SPM_THRESHOLD]
    a2.bar(["Rata-rata", "Maksimum", "Baku mutu"], vals, color=[NAVY, "#3b82f6", RED], width=0.6)
    for i, y in enumerate(vals):
        a2.text(i, y + 4, fmt(y, 1), ha="center", fontsize=7)
    a2.set_ylim(0, SPM_THRESHOLD * 1.13)
    a2.set_title("Dibanding Baku Mutu", loc="left")
    a2.tick_params(axis="x", labelsize=7)
    return to_data_uri(fig)


def _spm_gaps(spm, period):
    """Jadwal 6-harian dan tanggal yang tidak ada datanya.

    Jadwal dihitung mundur ke awal periode dari sampel pertama, dan hanya sampai sampel
    terakhir: bulan setelahnya mungkin belum dikirim pusat, bukan berarti sampel hilang.
    """
    dates = {r.timestamp for r in spm}
    t = spm[0].timestamp
    while t - datetime.timedelta(days=SPM_INTERVAL_DAYS) >= period.start:
        t -= datetime.timedelta(days=SPM_INTERVAL_DAYS)
    expected = []
    while t <= spm[-1].timestamp:
        expected.append(t)
        t += datetime.timedelta(days=SPM_INTERVAL_DAYS)
    tolerant = {d + datetime.timedelta(days=k) for d in dates for k in (-1, 0, 1)}
    return expected, [d for d in expected if d not in tolerant]


def build(period):
    kah = list(KAHSeriesData.objects.filter(bulan__gte=period.start_ym, bulan__lte=period.end_ym)
               .order_by("bulan", "minggu", "id"))
    spm = list(SPMSeriesData.objects.filter(timestamp__range=(period.start, period.end), spm__isnull=False)
               .order_by("timestamp"))
    med = _qc(kah)
    valid = [r for r in kah if not r.is_empty]
    ok = [r for r in valid if r.qc == "Lolos QC"]
    ph_ok = [r.ph for r in ok]
    expected, missing = _spm_gaps(spm, period) if spm else ([], [])

    monthly = []
    for y, m in period.months:
        ym = f"{y}-{m:02d}"
        mv = [r for r in valid if r.bulan == ym]
        mo = [r for r in ok if r.bulan == ym]
        ms = [r.spm for r in spm if (r.timestamp.year, r.timestamp.month) == (y, m)]
        monthly.append({
            "label": f"{BULAN[m]} {y}", "n": len(mv), "nok": len(mo),
            "ph_mean": st.mean(r.ph for r in mo) if mo else None,
            "ph_min": min((r.ph for r in mo), default=None), "ph_max": max((r.ph for r in mo), default=None),
            "acid": sum(1 for r in mo if r.ph < 5.6),
            "spm_n": len(ms), "spm_mean": st.mean(ms) if ms else None, "spm_max": max(ms) if ms else None,
        })

    spm_vals = [r.spm for r in spm]
    for r in spm:
        r.pct = 100 * r.spm / SPM_THRESHOLD
    return {
        "kah": kah, "valid": valid, "ok": ok, "empty": [r for r in kah if r.is_empty],
        "verify": [r for r in valid if r.qc.startswith("Perlu")],
        "ac_bad": [r for r in valid if r.ac_inconsistent],
        "median": med, "monthly": monthly,
        "ph_mean": st.mean(ph_ok) if ph_ok else None,
        "ph_min": min(ph_ok, default=None), "ph_max": max(ph_ok, default=None),
        "acid": sum(1 for p in ph_ok if p < 5.6),
        "acid_pct": 100 * sum(1 for p in ph_ok if p < 5.6) / len(ph_ok) if ph_ok else None,
        "spm": spm, "spm_expected": len(expected), "spm_missing": missing,
        "spm_mean": st.mean(spm_vals) if spm_vals else None,
        "spm_min": min(spm_vals, default=None), "spm_max": max(spm_vals, default=None),
        "spm_max_pct": 100 * max(spm_vals) / SPM_THRESHOLD if spm_vals else None,
        "spm_exceed": sum(1 for v in spm_vals if v > SPM_THRESHOLD),
        "spm_threshold": SPM_THRESHOLD,
        "param_info": [{"code": k, **v} for k, v in KAH_PARAM_INFO.items()],
        "chart_ph": _ph_chart(kah) if valid else None,
        "chart_ion": _ion_chart(kah) if valid else None,
        "chart_spm": _spm_chart(spm) if spm else None,
    }
