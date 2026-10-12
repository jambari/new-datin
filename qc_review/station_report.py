"""Daily station-health report: PDF + Telegram.

build_pdf(day) renders the findings of one UTC day (Indonesian + English)
and a 7-day station grid with reportlab (already used by qc_review's PDF
export). send_daily_report(day) posts the PDF to the Telegram group with a
short caption; if the scproc job has not delivered that day, it sends a
warning message instead so a missing report never goes unnoticed.
"""
from __future__ import annotations

import io
import logging
from collections import defaultdict
from datetime import date, timedelta
from xml.sax.saxutils import escape

from django.conf import settings
from django.utils import timezone

from theme.telegram import esc, send_telegram_document, send_telegram_message

from . import station_rules
from .models import StationDailyQC, StationDiagnosis
from .station_views import COMPONENT_ORDER

log = logging.getLogger(__name__)

GRID_DAYS = 7
SEV_COLORS = {"red": "#dc2626", "yellow": "#d97706", "green": "#16a34a"}
SEV_LABEL = {"red": "MERAH / RED", "yellow": "KUNING / YELLOW", "green": "BAIK / OK"}


def _chat_id():
    return getattr(settings, "STATION_QC_TELEGRAM_CHAT_ID", "") or None


def report_data(day: date) -> dict:
    rows = list(StationDailyQC.objects.filter(day=day).values(
        "network", "station", "location", "channel", "status"))
    findings = sorted(
        StationDiagnosis.objects.filter(day=day, severity__in=("red", "yellow")),
        key=lambda d: (d.severity != "red", d.network, d.station, d.channel, d.code))

    station_sev = defaultdict(list)
    for r in rows:
        station_sev[(r["network"], r["station"])].append(r["status"])
    worst = {k: station_rules.worst(v) for k, v in station_sev.items()}
    counts = defaultdict(int)
    for sev in worst.values():
        counts[sev] += 1

    since = day - timedelta(days=GRID_DAYS - 1)
    grid = defaultdict(lambda: defaultdict(list))
    for r in StationDailyQC.objects.filter(day__gte=since, day__lte=day).values(
            "network", "station", "day", "status"):
        grid[(r["network"], r["station"])][r["day"]].append(r["status"])
    n_find = defaultdict(lambda: defaultdict(int))
    for d in StationDiagnosis.objects.filter(day__gte=since, day__lte=day,
                                             severity__in=("red", "yellow")):
        n_find[(d.network, d.station)][d.day] += 1

    # Same rule on several components of one sensor (e.g. data gaps on SHE,
    # SHN and SHZ) reads better as one row listing all affected channels.
    groups = {}
    for f in findings:
        key = (f.network, f.station, f.location, f.code, f.severity)
        g = groups.setdefault(key, {"finding": f, "channels": []})
        if f.channel:
            g["channels"].append(f.channel)
    rows_grouped = []
    for (net, sta, loc, _code, sev), g in groups.items():
        f = g["finding"]
        chans = sorted(g["channels"], key=lambda c: (c[:2], COMPONENT_ORDER.get(c[-1:], 9), c))
        msg_id, msg_en = f.message_id, f.message_en
        if len(chans) > 1:
            # "SHE (horizontal timur-barat)" -> "SHZ/SHN/SHE": the component
            # name only fitted the first channel.
            joined = "/".join(chans)
            name_id, name_en = station_rules._comp_name(f.channel)
            msg_id = msg_id.replace(f"{f.channel} ({name_id})", f.channel).replace(f.channel, joined, 1)
            msg_en = msg_en.replace(f"{f.channel} ({name_en})", f.channel).replace(f.channel, joined, 1)
        label = ", ".join(f"{loc}.{c}" if loc else c for c in chans) or "semua / all"
        rows_grouped.append({"station": f"{net}.{sta}", "channels": label, "severity": sev,
                             "message_id": msg_id, "message_en": msg_en})

    days = [since + timedelta(days=i) for i in range(GRID_DAYS)]
    grid_rows = [{
        "station": f"{net}.{sta}",
        "cells": [(station_rules.worst(grid[(net, sta)][d]) if grid[(net, sta)].get(d) else None,
                   n_find[(net, sta)].get(d, 0)) for d in days],
    } for (net, sta) in sorted(grid)]

    return {"day": day, "n_stations": len(worst), "n_channels": len(rows),
            "counts": dict(counts), "worst": worst, "findings": findings,
            "finding_rows": rows_grouped,
            "days": days, "grid": grid_rows}


def build_pdf(day: date, data: dict | None = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)

    data = data or report_data(day)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.4 * cm, rightMargin=1.4 * cm,
                            topMargin=1.4 * cm, bottomMargin=1.4 * cm,
                            title=f"Station health {day.isoformat()}")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=14, leading=17)
    h2 = ParagraphStyle("h2", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=10.5,
                        leading=13, spaceBefore=10, spaceAfter=5)
    sub = ParagraphStyle("sub", parent=ss["Normal"], fontSize=8, textColor=colors.HexColor("#555555"))
    small = ParagraphStyle("small", parent=ss["Normal"], fontSize=7.5, leading=9.2)
    small_en = ParagraphStyle("small_en", parent=small, textColor=colors.HexColor("#6b7280"))
    cell = ParagraphStyle("cell", parent=small, alignment=TA_CENTER, textColor=colors.white,
                          fontName="Helvetica-Bold")

    now_wit = timezone.now().astimezone(timezone.get_fixed_timezone(9 * 60))
    story = [
        Paragraph("Laporan Harian Kesehatan Stasiun Seismik", h1),
        Paragraph("Daily Seismic Station Health Report", sub),
        Spacer(1, 4),
        Paragraph(f"Tanggal data / data day: <b>{day.strftime('%d-%m-%Y')}</b> (UTC) · "
                  f"dibuat / generated {now_wit.strftime('%d-%m-%Y %H:%M')} WIT · "
                  f"Stasiun Geofisika Kelas I Jayapura", sub),
        Spacer(1, 8),
    ]

    c = data["counts"]
    summary = Table([[
        Paragraph(f"<b>{data['n_stations']}</b> stasiun / stations<br/>{data['n_channels']} kanal / channels", small),
        Paragraph(f"<font color='{SEV_COLORS['red']}'><b>{c.get('red', 0)}</b></font> merah / red", small),
        Paragraph(f"<font color='{SEV_COLORS['yellow']}'><b>{c.get('yellow', 0)}</b></font> kuning / yellow", small),
        Paragraph(f"<font color='{SEV_COLORS['green']}'><b>{c.get('green', 0)}</b></font> baik / ok", small),
    ]], colWidths=[5 * cm, 4 * cm, 4 * cm, 4 * cm])
    summary.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f9fafb")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [summary, Paragraph("Temuan / Findings", h2)]

    if data["finding_rows"]:
        rows = [[Paragraph(f"<b>{h}</b>", small) for h in
                 ("No", "Stasiun / Station", "Kanal / Channel", "Status", "Temuan (ID) / Finding (EN)")]]
        for i, f in enumerate(data["finding_rows"], 1):
            rows.append([
                Paragraph(str(i), small),
                Paragraph(escape(f["station"]), small),
                Paragraph(escape(f["channels"]), small),
                Paragraph(f"<font color='{SEV_COLORS[f['severity']]}'><b>{f['severity'].upper()}</b></font>", small),
                [Paragraph(escape(f["message_id"]), small), Paragraph(escape(f["message_en"]), small_en)],
            ])
        t = Table(rows, colWidths=[0.8 * cm, 2.2 * cm, 2.4 * cm, 1.7 * cm, 11.1 * cm], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("Tidak ada masalah terdeteksi. / No issues detected.", small))

    story += [PageBreak(), Paragraph(f"Riwayat {GRID_DAYS} hari / {GRID_DAYS}-day history", h2),
              Paragraph("Warna = status terburuk stasiun per hari; angka = jumlah temuan. "
                        "Colour = worst station status per day; number = findings count. "
                        "Abu-abu / grey = tidak ada data QC / no QC data.", sub), Spacer(1, 5)]
    header = [Paragraph("<b>Stasiun</b>", small)] + [
        Paragraph(f"<b>{d.strftime('%d/%m')}</b>", ParagraphStyle("hd", parent=small, alignment=TA_CENTER))
        for d in data["days"]]
    grid_rows, styles = [header], []
    for r_i, row in enumerate(data["grid"], 1):
        line = [Paragraph(escape(row["station"]), small)]
        for c_i, (sev, n) in enumerate(row["cells"], 1):
            line.append(Paragraph(str(n) if n else "", cell))
            styles.append(("BACKGROUND", (c_i, r_i), (c_i, r_i),
                           colors.HexColor(SEV_COLORS.get(sev, "#e5e7eb"))))
        grid_rows.append(line)
    g = Table(grid_rows, colWidths=[3.2 * cm] + [1.6 * cm] * GRID_DAYS, repeatRows=1)
    g.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
    ] + styles))
    story.append(g)

    site = getattr(settings, "SITE_URL", "").rstrip("/")
    if site:
        story += [Spacer(1, 8), Paragraph(f"Detail: {escape(site)}/qc/stations/", sub)]
    doc.build(story)
    return buf.getvalue()


def build_caption(data: dict) -> str:
    c = data["counts"]
    day = data["day"].strftime("%d-%m-%Y")
    lines = [f"<b>Laporan Kesehatan Stasiun / Station Health</b> — {day} (UTC)",
             f"{data['n_stations']} stasiun: 🔴 {c.get('red', 0)} · 🟡 {c.get('yellow', 0)} · 🟢 {c.get('green', 0)}"]
    # {station: {code: [channels]}} -> "• IA.ARMI: Komponen rusak (SHZ)"
    red = defaultdict(lambda: defaultdict(list))
    for f in data["findings"]:
        if f.severity == "red":
            red[f"{f.network}.{f.station}"][f.code].append(f.channel)
    if red:
        lines.append("")
        lines.append("<b>Masalah:</b>")
        for sta in sorted(red):
            parts = []
            for code, chans in sorted(red[sta].items()):
                label = station_rules.CODE_LABELS_ID.get(code, code)
                chans = [c for c in chans if c]
                # Listing all three components adds nothing; name them only when partial.
                parts.append(f"{label} ({', '.join(chans)})" if 0 < len(chans) < 3 else label)
            lines.append(f"• {esc(sta)}: {esc('; '.join(parts))}")
    site = getattr(settings, "SITE_URL", "").rstrip("/")
    if site:
        lines += ["", f"{esc(site)}/qc/stations/"]
    caption = "\n".join(lines)
    return caption if len(caption) <= 1024 else caption[:1000] + "\n…"


def send_daily_report(day: date | None = None) -> bool:
    """Send the report for `day` (default: yesterday UTC). Never raises."""
    day = day or (timezone.now().date() - timedelta(days=1))   # TIME_ZONE is UTC
    try:
        data = report_data(day)
        if not data["n_channels"]:
            return send_telegram_message(
                f"⚠️ <b>Laporan Kesehatan Stasiun {day.strftime('%d-%m-%Y')}</b>: data QC belum masuk "
                f"dari scproc (job harian station_qc). Periksa ~/logs/station_qc.log di 192.168.1.5.\n"
                f"Station health data for this day has not arrived from scproc.",
                chat_id=_chat_id())
        pdf = build_pdf(day, data)
        return send_telegram_document(pdf, f"kesehatan-stasiun-{day.isoformat()}.pdf",
                                      caption=build_caption(data), chat_id=_chat_id())
    except Exception:
        log.exception("station health report for %s failed", day)
        return False
