"""Station waveform health: daily ingest API + analyst pages.

The scproc station-QC job POSTs one JSON batch per UTC day:

    {"day": "2026-10-12",
     "stations": [{"network": "IA", "station": "JAY",
                   "channels": [{"location": "", "channel": "BHZ",
                                 "sampling_rate": 20.0,
                                 "metrics": {...}}, ...]}, ...]}

For every station the channel rows are upserted, the diagnosis rules in
station_rules.py are run against the station's last BASELINE_DAYS days,
and that station-day's diagnoses are replaced. The daily job sends
"complete": true, so channels silent for up to EXPECTED_DAYS are kept in the
report as "no data since <date>".
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, timedelta

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Max
from django.shortcuts import render
from django.utils.dateparse import parse_date
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import station_rules
from .models import StationDailyQC, StationDiagnosis, StationMedia

BASELINE_DAYS = 14
EXPECTED_DAYS = 60      # channels with data in this window are expected every day
COMPONENT_ORDER = {"Z": 0, "N": 1, "1": 1, "E": 2, "2": 2}
# Metrics that only station_media.py sends; the daily job must not wipe them when it re-posts a day.
MEDIA_METRICS = ("sensor", "sensitivity", "rms_um_s", "dc_pct_full_scale", "ppsd_error", "psd_hours",
                 "psd_median_db_1s", "psd_above_nhnm_pct", "psd_below_nlnm_pct", "psd_spread_db")
CODE_RE = re.compile(r"^[A-Z0-9]{1,8}$")
MEDIA_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,80}\.png$")
MEDIA_MAX_BYTES = 5 * 1024 * 1024
MEDIA_MAX_FILES = 30


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@api_view(["POST"])
@parser_classes([JSONParser])
@permission_classes([IsAuthenticated])
def ingest_station_daily(request):
    day = parse_date(str(request.data.get("day", "")))
    stations = request.data.get("stations")
    if day is None or not isinstance(stations, list):
        return Response({"detail": "need 'day' (YYYY-MM-DD) and 'stations' list"}, status=400)
    n_channels, n_diag = ingest_day(day, stations, complete=bool(request.data.get("complete")))
    return Response({"day": day.isoformat(), "stations": len(stations),
                     "channels": n_channels, "diagnoses": n_diag})


def ingest_day(day: date, stations: list[dict], complete: bool = False) -> tuple[int, int]:
    """Store one day's channel metrics and (re)evaluate the diagnoses.

    complete=True means the batch covers the whole archive for that day (the
    daily job, not a --stations subset). Channels that had data in the last
    EXPECTED_DAYS but are missing from the batch are then added with 0%
    availability, so a station that went silent stays in the report instead
    of quietly disappearing.
    """
    by_station: dict[tuple[str, str], dict[tuple[str, str], dict]] = defaultdict(dict)
    for st in stations:
        net, sta = st.get("network"), st.get("station")
        if not net or not sta:
            continue
        for c in st.get("channels") or []:
            if c.get("channel"):
                by_station[(net, sta)][(c.get("location") or "", c["channel"])] = c

    if complete:
        expected = (StationDailyQC.objects
                    .filter(day__lt=day, day__gte=day - timedelta(days=EXPECTED_DAYS),
                            metrics__availability_pct__gt=0)
                    .values_list("network", "station", "location", "channel").distinct())
        for net, sta, loc, cha in expected:
            by_station[(net, sta)].setdefault((loc, cha), {
                "location": loc, "channel": cha,
                "metrics": {"availability_pct": 0.0, "not_in_archive": True}})

    n_channels = n_diag = 0
    for (net, sta), chans in by_station.items():
        n_channels += len(chans)
        n_diag += _store_station_day(net, sta, day, list(chans.values()))
    return n_channels, n_diag


@api_view(["POST"])
@parser_classes([MultiPartParser])
@permission_classes([IsAuthenticated])
def ingest_station_media(request):
    """One station-day of spectra and PNGs from scripts/station_qc/station_media.py."""
    try:
        payload = json.loads(request.data.get("payload") or "")
    except ValueError:
        return Response({"detail": "payload must be JSON"}, status=400)
    day = parse_date(str(payload.get("day", "")))
    net, sta = str(payload.get("network", "")), str(payload.get("station", ""))
    if day is None or not CODE_RE.match(net) or not CODE_RE.match(sta):
        return Response({"detail": "need day, network and station"}, status=400)
    files = request.FILES.getlist("files")
    if len(files) > MEDIA_MAX_FILES:
        return Response({"detail": "too many files"}, status=400)
    for f in files:
        if not MEDIA_NAME_RE.match(f.name) or f.size > MEDIA_MAX_BYTES or f.read(8) != b"\x89PNG\r\n\x1a\n":
            return Response({"detail": f"bad file {f.name!r}"}, status=400)
        f.seek(0)

    saved = {}
    for f in files:
        path = f"qc_stations/{day.isoformat()}/{net}.{sta}/{f.name}"
        if default_storage.exists(path):
            default_storage.delete(path)
        saved[f.name] = default_storage.save(path, f)

    images = {k: saved[v] for k, v in (payload.get("images") or {}).items() if v in saved}
    chan_images = {}
    existing = {(r.location, r.channel): r for r in StationDailyQC.objects.filter(network=net, station=sta, day=day)}
    channels = {key: {"location": key[0], "channel": key[1], "sampling_rate": r.sampling_rate, "metrics": dict(r.metrics)}
                for key, r in existing.items()}
    for c in payload.get("channels") or []:
        cha = str(c.get("channel", ""))
        if not cha:
            continue
        key = (str(c.get("location") or ""), cha)
        row = channels.setdefault(key, {"location": key[0], "channel": cha, "sampling_rate": None, "metrics": {}})
        row["metrics"].update({k: v for k, v in (c.get("metrics") or {}).items() if k in MEDIA_METRICS})
        kept = {k: saved[v] for k, v in (c.get("images") or {}).items() if v in saved}
        if kept:
            chan_images[f"{key[0]}.{cha}"] = kept
    images["channels"] = chan_images
    StationMedia.objects.update_or_create(network=net, station=sta, day=day, defaults={
        "site": str(payload.get("site") or "")[:120], "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"), "elevation": payload.get("elevation"),
        "hvsr": payload.get("hvsr"), "images": images})
    n_diag = _store_station_day(net, sta, day, list(channels.values())) if channels else 0
    return Response({"day": day.isoformat(), "station": sta, "images": len(saved), "diagnoses": n_diag})


def purge_station_media(today: date | None = None) -> int:
    """Delete image files older than STATION_MEDIA_KEEP_DAYS, keeping rows and numbers."""
    today = today or date.today()
    cutoff = today - timedelta(days=settings.STATION_MEDIA_KEEP_DAYS)
    n = 0
    for row in StationMedia.objects.filter(day__lt=cutoff).exclude(images={}):
        for path in _image_paths(row.images):
            default_storage.delete(path)
            n += 1
        row.images = {}
        row.save(update_fields=["images"])
    return n


def _image_paths(images: dict) -> list[str]:
    paths = [v for k, v in images.items() if k != "channels"]
    for per_channel in (images.get("channels") or {}).values():
        paths.extend(per_channel.values())
    return paths


def _add_last_data_day(net, sta, day, loc, cha, metrics: dict) -> dict:
    """For a channel without data: when did it last have data?"""
    if (metrics.get("availability_pct") or 0) > 0 or metrics.get("last_data_day"):
        return metrics                  # the worker reports it for long-silent stations
    last = (StationDailyQC.objects
            .filter(network=net, station=sta, location=loc, channel=cha,
                    day__lt=day, metrics__availability_pct__gt=0)
            .aggregate(d=Max("day"))["d"])
    metrics = dict(metrics)
    if last:
        metrics["last_data_day"] = last.isoformat()
        metrics["days_without_data"] = (day - last).days
    return metrics


@transaction.atomic
def _store_station_day(net: str, sta: str, day: date, channels: list[dict]) -> int:
    rows = {}
    for c in channels:
        loc = c.get("location") or ""
        metrics = _add_last_data_day(net, sta, day, loc, c["channel"], c.get("metrics") or {})
        old = StationDailyQC.objects.filter(network=net, station=sta, location=loc, channel=c["channel"],
                                            day=day).values_list("metrics", flat=True).first() or {}
        metrics = {**{k: old[k] for k in MEDIA_METRICS if k in old}, **metrics}
        row, _ = StationDailyQC.objects.update_or_create(
            network=net, station=sta, location=loc, channel=c["channel"], day=day,
            defaults={"sampling_rate": c.get("sampling_rate"), "metrics": metrics},
        )
        rows[(loc, c["channel"])] = row

    history = defaultdict(list)
    for h in (StationDailyQC.objects
              .filter(network=net, station=sta,
                      day__lt=day, day__gte=day - timedelta(days=BASELINE_DAYS))
              .order_by("day").values("location", "channel", "metrics")):
        history[(h["location"], h["channel"])].append(h["metrics"])

    findings = station_rules.evaluate(
        [{"location": loc, "channel": cha, "metrics": r.metrics} for (loc, cha), r in rows.items()],
        history)

    StationDiagnosis.objects.filter(network=net, station=sta, day=day).delete()
    StationDiagnosis.objects.bulk_create([
        StationDiagnosis(network=net, station=sta, location=f.location, channel=f.channel,
                         day=day, code=f.code, severity=f.severity,
                         message_id=f.message_id, message_en=f.message_en,
                         evidence=f.evidence)
        for f in findings])

    station_wide = [f.severity for f in findings if not f.channel]
    for (loc, cha), row in rows.items():
        sev = station_rules.worst(
            station_wide + [f.severity for f in findings if f.channel == cha and f.location == loc])
        if row.status != sev:
            row.status = sev
            row.save(update_fields=["status"])
    return len(findings)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def _channel_sort_key(loc_cha):
    loc, cha = loc_cha
    return (loc, cha[:2], COMPONENT_ORDER.get(cha[-1:], 9), cha)


def _picked_day(request, newest: date) -> date:
    """The ?day= being viewed, never past the newest day with data."""
    picked = parse_date(request.GET.get("day", "") or "") if request.GET.get("day") else None
    return min(picked, newest) if picked else newest


def station_health(request):
    """Grid of station × component × day, plus the latest day's findings."""
    try:
        n_days = max(7, min(60, int(request.GET.get("days", 30))))
    except ValueError:
        n_days = 30
    newest = StationDailyQC.objects.aggregate(d=Max("day"))["d"]
    if newest is None:
        return render(request, "qc_review/station_health.html", {"empty": True})
    latest = _picked_day(request, newest)
    status_filter = request.GET.get("status", "")
    query = request.GET.get("q", "").strip().upper()

    days = [latest - timedelta(days=i) for i in range(n_days - 1, -1, -1)]
    cells = defaultdict(dict)       # (net, sta) -> {(loc, cha): {day: status}}
    for r in StationDailyQC.objects.filter(day__gte=days[0], day__lte=latest).values(
            "network", "station", "location", "channel", "day", "status"):
        cells[(r["network"], r["station"])].setdefault(
            (r["location"], r["channel"]), {})[r["day"]] = r["status"]

    issue_rank = {"red": 0, "yellow": 1}
    issues = sorted(
        StationDiagnosis.objects.filter(day=latest, severity__in=issue_rank),
        key=lambda d: (issue_rank[d.severity], d.network, d.station, d.channel))

    grid = []
    for (net, sta) in sorted(cells):
        chans = cells[(net, sta)]
        grid.append({
            "network": net, "station": sta,
            "rows": [{"location": loc, "channel": cha,
                      "cells": [chans[(loc, cha)].get(d, "none") for d in days]}
                     for (loc, cha) in sorted(chans, key=_channel_sort_key)],
        })

    counts = defaultdict(int)
    for st in grid:
        st["status"] = station_rules.worst(r["cells"][-1] for r in st["rows"])
        counts[st["status"]] += 1
    n_all = len(grid)
    grid = [st for st in grid if (not status_filter or st["status"] == status_filter)
            and (not query or query in f'{st["network"]}.{st["station"]}')]
    shown = {(st["network"], st["station"]) for st in grid}
    issues = [d for d in issues if (d.network, d.station) in shown]

    return render(request, "qc_review/station_health.html", {
        "days": days, "latest": latest, "grid": grid, "issues": issues,
        "n_days": n_days, "counts": dict(counts), "n_stations": n_all, "n_shown": len(grid),
        "status_filter": status_filter, "query": query,
        "prev_day": latest - timedelta(days=1), "next_day": latest + timedelta(days=1) if latest < newest else None,
    })


def station_health_detail(request, network, station):
    """One station: findings history and the latest metrics per channel."""
    newest = (StationDailyQC.objects.filter(network=network, station=station)
              .aggregate(d=Max("day"))["d"])
    latest = _picked_day(request, newest) if newest else None
    if latest is None:
        return render(request, "qc_review/station_health_detail.html",
                      {"network": network, "station": station, "empty": True}, status=404)

    since = latest - timedelta(days=29)
    rows = list(StationDailyQC.objects.filter(network=network, station=station,
                                              day__gte=since).order_by("day"))
    days = sorted({r.day for r in rows})
    by_chan = defaultdict(dict)
    for r in rows:
        by_chan[(r.location, r.channel)][r.day] = r
    channels = []
    for key in sorted(by_chan, key=_channel_sort_key):
        last = by_chan[key].get(latest)
        channels.append({
            "location": key[0], "channel": key[1],
            "strip": [(d, by_chan[key][d].status if d in by_chan[key] else "none") for d in days],
            "latest": last.metrics if last else None,
            "status": last.status if last else "none",
        })

    diagnoses = StationDiagnosis.objects.filter(
        network=network, station=station, day__gte=since).order_by("-day", "channel", "code")

    media = StationMedia.objects.filter(network=network, station=station, day=latest).first()
    station_images, ppsd = [], []
    if media:
        label = {"overview": "Ringkasan 24 jam · 24 h overview", "hvsr": "HVSR noise · Noise HVSR"}
        station_images = [(label[k], default_storage.url(media.images[k])) for k in label if k in media.images]
        for c in channels:
            path = ((media.images.get("channels") or {}).get(f'{c["location"]}.{c["channel"]}') or {}).get("ppsd")
            if path:
                ppsd.append((f'{c["location"] + "." if c["location"] else ""}{c["channel"]}', default_storage.url(path)))

    return render(request, "qc_review/station_health_detail.html", {
        "network": network, "station": station, "latest": latest,
        "channels": channels, "diagnoses": diagnoses, "media": media,
        "station_images": station_images, "ppsd_images": ppsd,
        "prev_day": latest - timedelta(days=1), "next_day": latest + timedelta(days=1) if latest < newest else None,
    })
