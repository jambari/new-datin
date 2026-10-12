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

from collections import defaultdict
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Max
from django.shortcuts import render
from django.utils.dateparse import parse_date
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import station_rules
from .models import StationDailyQC, StationDiagnosis

BASELINE_DAYS = 14
EXPECTED_DAYS = 60      # channels with data in this window are expected every day
COMPONENT_ORDER = {"Z": 0, "N": 1, "1": 1, "E": 2, "2": 2}


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


def _add_last_data_day(net, sta, day, loc, cha, metrics: dict) -> dict:
    """For a channel without data: when did it last have data?"""
    if (metrics.get("availability_pct") or 0) > 0:
        return metrics
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


def station_health(request):
    """Grid of station × component × day, plus the latest day's findings."""
    try:
        n_days = max(7, min(60, int(request.GET.get("days", 14))))
    except ValueError:
        n_days = 14
    latest = StationDailyQC.objects.aggregate(d=Max("day"))["d"]
    if latest is None:
        return render(request, "qc_review/station_health.html", {"empty": True})

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
        sev = station_rules.worst(r["cells"][-1] for r in st["rows"])
        counts[sev] += 1

    return render(request, "qc_review/station_health.html", {
        "days": days, "latest": latest, "grid": grid, "issues": issues,
        "n_days": n_days, "counts": dict(counts), "n_stations": len(grid),
    })


def station_health_detail(request, network, station):
    """One station: findings history and the latest metrics per channel."""
    latest = (StationDailyQC.objects.filter(network=network, station=station)
              .aggregate(d=Max("day"))["d"])
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

    return render(request, "qc_review/station_health_detail.html", {
        "network": network, "station": station, "latest": latest,
        "channels": channels, "diagnoses": diagnoses,
    })
