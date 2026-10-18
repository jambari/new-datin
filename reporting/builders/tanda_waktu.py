"""Laporan layanan informasi tanda waktu: terbit dan terbenam Matahari (almanac.SunMoonEvent).

Baris SunMoonEvent dihitung per hari UTC (fill_sunmoon), sehingga terbit pada baris tanggal D
jatuh pada pagi D+1 WIT. Di sini setiap waktu dikelompokkan menurut tanggal WIT-nya sendiri.
"""
import datetime
import statistics as st
from collections import defaultdict

from django.conf import settings
from matplotlib.dates import DateFormatter
from matplotlib.ticker import FuncFormatter

from almanac.models import SunMoonEvent
from reporting.charts import NAVY, new_figure, to_data_uri
from reporting.common import BULAN
from reporting.osm import ATTRIBUTION, StaticMap

TITLE = "Terlaksananya layanan informasi tanda waktu di Wilayah Papua dan Sekitarnya"
WIT = datetime.timezone(datetime.timedelta(hours=9))
HOME = "Jayapura"
LABEL_LEFT = {"Sentani"}                        # hindari label bertumpuk dengan Jayapura
PUBLIC_URL = "https://stageof-jayapura.bmkg.go.id/ttm/"


def _hm(t):
    return t.strftime("%H:%M") if t else "–"


def _minutes(t):
    return t.hour * 60 + t.minute + t.second / 60


def _dur(minutes):
    if minutes is None:
        return "–"
    m = int(round(minutes))
    return f"{m // 60} j {m % 60:02d} m"


def _map(cities):
    smap = StaticMap(-9.3, 0.4, 129.8, 141.6, zoom=6)
    fig, ax = new_figure(7.0, 7.0 * smap.height / smap.width)
    ax.imshow(smap.image, extent=(0, smap.width, smap.height, 0))
    ax.grid(False)
    for c in cities:
        x, y = smap.project(c["lat"], c["lon"])
        home = c["name"] == HOME
        ax.plot(x, y, marker="*" if home else "o", ms=11 if home else 5.5, mfc="#f59e0b" if home else NAVY,
                mec="white", mew=0.8, ls="")
        left = c["name"] in LABEL_LEFT
        ax.annotate(c["name"], (x, y), xytext=(-4 if left else 4, 3), textcoords="offset points", fontsize=6.5,
                    ha="right" if left else "left",
                    fontweight="bold" if home else "normal",
                    bbox=dict(boxstyle="round,pad=.12", fc="white", ec="none", alpha=0.75))
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlim(0, smap.width)
    ax.set_ylim(smap.height, 0)
    ax.text(smap.width - 4, smap.height - 4, ATTRIBUTION, ha="right", va="bottom", fontsize=6.5,
            bbox=dict(fc="white", ec="none", alpha=0.8, pad=1.5))
    ax.set_title("Lokasi Layanan Informasi Terbit dan Terbenam Matahari", loc="left")
    return to_data_uri(fig, dpi=150)


def _chart(days, table):
    fig, axs = new_figure(7.4, 2.8, ncols=2)
    for ax, key, title in ((axs[0], "rise", "Terbit Matahari (WIT)"), (axs[1], "set", "Terbenam Matahari (WIT)")):
        lo, hi, home = [], [], []
        for d in days:
            vals = [_minutes(table[c][d][key]) for c in table if table[c].get(d, {}).get(key)]
            lo.append(min(vals) if vals else None)
            hi.append(max(vals) if vals else None)
            h = table.get(HOME, {}).get(d, {}).get(key)
            home.append(_minutes(h) if h else None)
        ax.fill_between(days, [v / 60 if v is not None else float("nan") for v in lo],
                        [v / 60 if v is not None else float("nan") for v in hi],
                        color="#93c5fd", alpha=0.5, lw=0, label="Rentang 20 lokasi")
        ax.plot(days, [v / 60 if v is not None else float("nan") for v in home], color=NAVY, lw=1.4, label=HOME)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v):02d}:{int(round(v % 1 * 60)) % 60:02d}"))
        ax.set_title(title, loc="left", fontsize=9)
        ax.xaxis.set_major_formatter(DateFormatter("%d/%m"))
        ax.tick_params(axis="x", labelsize=6.5, rotation=30)
        ax.tick_params(axis="y", labelsize=7)
        ax.legend(fontsize=6.5, loc="upper right", framealpha=0.9)
    fig.autofmt_xdate()
    fig.tight_layout()
    return to_data_uri(fig)


def build(period):
    cities = [dict(c) for c in getattr(settings, "SUNMOON_CITIES", [])]
    names = [c["name"] for c in cities]
    days = []
    d = period.start
    while d <= period.end:
        days.append(d)
        d += datetime.timedelta(days=1)
    day_set = set(days)
    table = defaultdict(lambda: defaultdict(dict))         # kota -> tanggal WIT -> {rise, set}
    qs = SunMoonEvent.objects.filter(date__gte=period.start - datetime.timedelta(days=1),
                                     date__lte=period.end + datetime.timedelta(days=1), city__in=names)
    for city, rise, sset in qs.values_list("city", "sun_rise", "sun_set"):
        for key, t in (("rise", rise), ("set", sset)):
            if t is None:
                continue
            local = t.astimezone(WIT)
            if local.date() in day_set:
                table[city][local.date()][key] = local.replace(tzinfo=None)

    summary = []
    for c in cities:
        rows = table.get(c["name"], {})
        rises = [rows[d]["rise"] for d in days if rows.get(d, {}).get("rise")]
        sets = [rows[d]["set"] for d in days if rows.get(d, {}).get("set")]
        lengths = [_minutes(rows[d]["set"]) - _minutes(rows[d]["rise"]) for d in days
                   if rows.get(d, {}).get("rise") and rows.get(d, {}).get("set")]
        summary.append({
            **c, "n": len(lengths),
            "rise_min": _hm(min(rises, key=_minutes)) if rises else "–",
            "rise_max": _hm(max(rises, key=_minutes)) if rises else "–",
            "set_min": _hm(min(sets, key=_minutes)) if sets else "–",
            "set_max": _hm(max(sets, key=_minutes)) if sets else "–",
            "day_len": _dur(st.mean(lengths)) if lengths else "–",
        })

    home_rows = table.get(HOME, {})
    home_months = []
    for y, m in period.months:
        rows = []
        for d in days:
            if (d.year, d.month) != (y, m):
                continue
            r = home_rows.get(d, {})
            length = (_minutes(r["set"]) - _minutes(r["rise"])) if r.get("rise") and r.get("set") else None
            rows.append({"date": d, "rise": _hm(r.get("rise")), "set": _hm(r.get("set")), "len": _dur(length)})
        home_months.append({"label": f"{BULAN[m]} {y}", "rows": rows})

    # Lampiran: semua lokasi pada tanggal 1, 15, dan akhir tiap bulan.
    sample_months = []
    for y, m in period.months:
        mdays = [d for d in days if (d.year, d.month) == (y, m)]
        picks = sorted({mdays[0], *(d for d in mdays if d.day == 15), mdays[-1]}) if mdays else []
        sample_months.append({
            "label": f"{BULAN[m]} {y}", "dates": picks,
            "rows": [{"name": c["name"],
                      "cells": [(_hm(table.get(c["name"], {}).get(d, {}).get("rise")),
                                 _hm(table.get(c["name"], {}).get(d, {}).get("set"))) for d in picks]}
                     for c in cities],
        })

    expected = len(days) * len(cities)
    complete = sum(s["n"] for s in summary)
    return {
        "cities": summary, "n_cities": len(cities), "n_days": len(days),
        "n_records": complete, "expected": expected,
        "completeness": 100.0 * complete / expected if expected else None,
        "home": HOME, "home_months": home_months, "sample_months": sample_months,
        "public_url": PUBLIC_URL,
        "map": _map(cities) if cities else None,
        "chart": _chart(days, table) if complete else None,
    }
