"""
Views
=====
Web pages:
  GET   /                                 event list
  GET   /event/<public_id>/               latest run review
  GET   /event/<public_id>/run/<n>/       a specific historical run
  POST  /station/<id>/review/             save reviewer note + action

API:
  POST  /api/qc-events/                   worker uploads here
  GET   /api/event/<public_id>/map.json   stations + epicenter as GeoJSON-ish
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from .models import Event, QCRun, StationResult
from .utils import get_on_duty_staff
from repository.utils import calculate_remark

import zoneinfo as _zi
_WIT = _zi.ZoneInfo("Asia/Jayapura")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _parse_iso(s):
    if not s:
        return None
    dt = parse_datetime(s)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# API: ingest
# ---------------------------------------------------------------------------

@api_view(["POST"])
@parser_classes([MultiPartParser])
def ingest_event(request):
    """Worker POSTs here after every SeisComP commit.

    Behaviour:
      - The Event row (matched by public_id) is updated in place with
        the latest hypocenter / magnitude / region.
      - A new QCRun is *always* created (run_number = previous + 1).
        Previous runs (and their reviewer notes) are preserved.

    Multipart fields:
        payload    : JSON {event: {...}, stations: [...], notes?: str}
        overview   : PNG, multi-station record section
        image_<i>  : PNG for stations[i]
        mseed_<i>  : MiniSEED for stations[i]
    """
    raw = request.data.get("payload")
    if not raw:
        return Response({"detail": "missing payload"}, status=400)
    try:
        body = json.loads(raw)
    except json.JSONDecodeError as e:
        return Response({"detail": f"bad JSON: {e}"}, status=400)

    ev_data = body.get("event") or {}
    stations = body.get("stations") or []
    run_notes = body.get("notes", "")

    pid = ev_data.get("public_id")
    if not pid:
        return Response({"detail": "event.public_id required"}, status=400)

    lat = ev_data["latitude"]
    lon = ev_data["longitude"]
    region = calculate_remark(lat, lon) or ev_data.get("region", "")

    event, created_event = Event.objects.update_or_create(
        public_id=pid,
        defaults={
            "origin_time": _parse_iso(ev_data.get("origin_time")),
            "latitude": lat,
            "longitude": lon,
            "depth_km": ev_data["depth_km"],
            "magnitude": ev_data.get("magnitude"),
            "magnitude_type": ev_data.get("magnitude_type"),
            "region": region,
        },
    )

    # New QCRun for THIS commit. We never overwrite past runs.
    last = event.runs.order_by("-run_number").first()
    next_n = (last.run_number + 1) if last else 1
    run = QCRun.objects.create(
        event=event,
        run_number=next_n,
        notes=run_notes,
        # Snapshot the parameters AS COMMITTED on this run. The Event
        # row will keep the latest values, but this run will always
        # show what the analyst saw at this commit.
        snap_origin_time=_parse_iso(ev_data.get("origin_time")),
        snap_latitude=lat,
        snap_longitude=lon,
        snap_depth_km=ev_data.get("depth_km"),
        snap_magnitude=ev_data.get("magnitude"),
        snap_magnitude_type=ev_data.get("magnitude_type"),
        snap_region=region,
        # SeisComP analyst-workflow state for this commit
        evaluation_mode=(ev_data.get("evaluation_mode") or "").lower() or None,
        evaluation_status=(ev_data.get("evaluation_status") or "").lower() or None,
    )

    overview = request.FILES.get("overview")
    if overview:
        run.overview_image.save(
            f"{event.public_id}_run{next_n}_overview.png",
            ContentFile(overview.read()), save=True,
        )

    created = []
    for i, sd in enumerate(stations):
        fmin, fmax = sd.get("filter_band", [None, None])
        sr = StationResult.objects.create(
            run=run,
            network=sd.get("network", ""),
            station=sd["station"],
            station_lat=sd.get("station_lat"),
            station_lon=sd.get("station_lon"),
            distance_deg=sd.get("distance_deg"),
            azimuth=sd.get("azimuth"),
            distance_class=sd.get("distance_class", "regional"),
            filter_freqmin=fmin or 1.0,
            filter_freqmax=fmax or 10.0,
            analyst_p=_parse_iso(sd.get("analyst_p")),
            analyst_s=_parse_iso(sd.get("analyst_s")),
            auto_p=_parse_iso(sd.get("auto_p")),
            auto_s=_parse_iso(sd.get("auto_s")),
            auto_p_prob=sd.get("auto_p_prob"),
            auto_s_prob=sd.get("auto_s_prob"),
            delta_p=sd.get("delta_p"),
            delta_s=sd.get("delta_s"),
            qc_flag=sd.get("qc_flag", "unknown"),
        )

        img = request.FILES.get(f"image_{i}")
        if img:
            sr.image.save(
                f"{event.public_id}_run{next_n}_{sr.network}_{sr.station}.png",
                ContentFile(img.read()), save=False,
            )
        ms = request.FILES.get(f"mseed_{i}")
        if ms:
            sr.waveform_file.save(
                f"{event.public_id}_run{next_n}_{sr.network}_{sr.station}.mseed",
                ContentFile(ms.read()), save=False,
            )
        sr.save()

        # Try to inherit reviewer notes from the previous run for the same
        # station — the senior analyst probably wants to see what the
        # junior reviewer said before the re-pick.
        if last is not None:
            prev = last.station_results.filter(
                network=sr.network, station=sr.station,
            ).first()
            if prev and prev.reviewer_note:
                sr.reviewer_note = (
                    f"[from run #{last.run_number}] {prev.reviewer_note}"
                )
                sr.save(update_fields=["reviewer_note"])

        created.append(sr.id)

    return Response(
        {"event_id": event.id,
         "public_id": event.public_id,
         "event_created": created_event,
         "run_number": run.run_number,
         "stations_created": len(created),
         "review_url": f"/event/{event.public_id}/"},
        status=status.HTTP_201_CREATED,
    )


# ---------------------------------------------------------------------------
# API: map data (used by the Leaflet view)
# ---------------------------------------------------------------------------

@api_view(["GET"])
def event_map_json(request, public_id):
    event = get_object_or_404(Event, public_id=public_id)
    run_n = request.GET.get("run")
    if run_n:
        run = get_object_or_404(QCRun, event=event, run_number=int(run_n))
    else:
        run = event.latest_run
    if not run:
        return JsonResponse({"epicenter": None, "stations": []})

    stations = []
    for s in run.station_results.all():
        if s.station_lat is None or s.station_lon is None:
            continue
        stations.append({
            "code": f"{s.network}.{s.station}",
            "lat": s.station_lat,
            "lon": s.station_lon,
            "qc_flag": s.qc_flag,
            "distance_deg": s.distance_deg,
            "delta_p": s.delta_p,
            "delta_s": s.delta_s,
        })

    return JsonResponse({
        "event": {
            "public_id": event.public_id,
            "lat": event.latitude,
            "lon": event.longitude,
            "depth_km": event.depth_km,
            "magnitude": event.magnitude,
        },
        "stations": stations,
        "run_number": run.run_number,
    })


# ---------------------------------------------------------------------------
# Web pages
# ---------------------------------------------------------------------------

def event_list(request):
    from jadwal.models import JadwalHarian, Pegawai
    from datetime import date, datetime, timedelta, timezone as _tz
    from django.db.models import Q

    qs = Event.objects.all().prefetch_related("runs").order_by("-origin_time")

    # ── filter: pegawai ──────────────────────────────────────────────────────
    pegawai_id = request.GET.get("pegawai", "").strip()
    today = date.today()
    pegawai_list = Pegawai.objects.filter(
        Q(tanggal_keluar__isnull=True) | Q(tanggal_keluar__gt=today)
    ).order_by("urutan", "nama")
    selected_pegawai = None
    if pegawai_id:
        try:
            selected_pegawai = Pegawai.objects.get(pk=int(pegawai_id))
            # Collect all (tanggal, pola) pairs for this pegawai
            jadwal_qs = (
                JadwalHarian.objects
                .filter(pegawai=selected_pegawai, pola__isnull=False, pola__is_libur=False)
                .select_related("pola")
            )
            # Build a set of WIT dates this pegawai was on shift.
            # We also store (date, start, end, overnight) to do exact time matching.
            shift_windows = []
            for j in jadwal_qs:
                shift_windows.append((
                    j.tanggal,
                    j.pola.jam_mulai,
                    j.pola.jam_selesai,
                    j.pola.jam_selesai < j.pola.jam_mulai,  # overnight
                ))
            # Filter events whose origin_time WIT falls within any shift window
            matching_ids = []
            for e in qs:
                if e.origin_time is None:
                    continue
                e_wit = e.origin_time.astimezone(_WIT)
                e_date = e_wit.date()
                e_time = e_wit.time()
                for (s_date, s_start, s_end, overnight) in shift_windows:
                    if not overnight:
                        if s_date == e_date and s_start <= e_time <= s_end:
                            matching_ids.append(e.pk)
                            break
                    else:
                        # Shift started on s_date, event either same day after start or next day before end
                        if s_date == e_date and e_time >= s_start:
                            matching_ids.append(e.pk)
                            break
                        if s_date == e_date - timedelta(days=1) and e_time <= s_end:
                            matching_ids.append(e.pk)
                            break
            qs = qs.filter(pk__in=matching_ids)
        except (ValueError, Pegawai.DoesNotExist):
            selected_pegawai = None

    # ── filter: date range (origin_time in WIT) ──────────────────────────────
    date_from_str = request.GET.get("date_from", "").strip()
    date_to_str   = request.GET.get("date_to", "").strip()
    date_from = date_to = None
    if date_from_str:
        try:
            date_from = date.fromisoformat(date_from_str)
            # WIT midnight → UTC
            dt_from_utc = datetime(date_from.year, date_from.month, date_from.day,
                                   tzinfo=_WIT).astimezone(_tz.utc)
            qs = qs.filter(origin_time__gte=dt_from_utc)
        except ValueError:
            date_from = None
    if date_to_str:
        try:
            date_to = date.fromisoformat(date_to_str)
            next_day = date_to + timedelta(days=1)
            dt_to_utc = datetime(next_day.year, next_day.month, next_day.day,
                                 tzinfo=_WIT).astimezone(_tz.utc)
            qs = qs.filter(origin_time__lt=dt_to_utc)
        except ValueError:
            date_to = None

    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    rows = []
    for e in page_obj:
        rows.append({
            "event":     e,
            "summary":   e.qc_summary,
            "run_count": e.run_count,
            "on_duty":   get_on_duty_staff(e.origin_time),
        })
    return render(request, "qc_review/event_list.html", {
        "rows":             rows,
        "page_obj":         page_obj,
        "pegawai_list":     pegawai_list,
        "selected_pegawai": selected_pegawai,
        "date_from":        date_from_str,
        "date_to":          date_to_str,
    })


import json as _json

def event_detail(request, public_id, run_number=None):
    event = get_object_or_404(Event, public_id=public_id)
    if run_number is None:
        run = event.latest_run
    else:
        run = get_object_or_404(QCRun, event=event, run_number=run_number)

    stations = list(run.station_results.all()) if run else []
    all_runs = event.runs.all()
    has_station_coords = any(
        s.station_lat is not None and s.station_lon is not None
        for s in stations
    )

    # Build a JSON-serialisable comparison structure for Tab 2.
    # Keeps all numeric values the template/JS needs in one place.
    comparison = []
    for s in stations:
        def _fmt(dt):
            return dt.strftime("%H:%M:%S.%f")[:-4] if dt else None

        comparison.append({
            "code":          f"{s.network}.{s.station}",
            "distance_deg":  s.distance_deg,
            "distance_class": s.distance_class,
            "qc_flag":       s.qc_flag,
            "analyst_p":     _fmt(s.analyst_p),
            "analyst_s":     _fmt(s.analyst_s),
            "auto_p":        _fmt(s.auto_p),
            "auto_s":        _fmt(s.auto_s),
            "auto_p_prob":   round(s.auto_p_prob, 3) if s.auto_p_prob is not None else None,
            "auto_s_prob":   round(s.auto_s_prob, 3) if s.auto_s_prob is not None else None,
            "delta_p":       round(s.delta_p, 3) if s.delta_p is not None else None,
            "delta_s":       round(s.delta_s, 3) if s.delta_s is not None else None,
            "filter_band":   f"{s.filter_freqmin:.1f}–{s.filter_freqmax:.1f} Hz",
            "reviewer_action": s.reviewer_action,
        })

    return render(request, "qc_review/event_detail.html", {
        "event": event,
        "run": run,
        "stations": stations,
        "summary": run.qc_summary if run else {},
        "all_runs": all_runs,
        "has_station_coords": has_station_coords,
        "comparison_json": _json.dumps(comparison),
        "on_duty":     get_on_duty_staff(event.origin_time),
        "on_duty_qc":  get_on_duty_staff(run.committed_at) if run else [],
    })


@require_POST
def station_review(request, station_id):
    sr = get_object_or_404(StationResult, id=station_id)
    sr.reviewer_note = request.POST.get("note", "")
    sr.reviewer_action = request.POST.get("action", "pending")
    sr.reviewer_name = request.POST.get("reviewer", "")[:64]
    sr.reviewed_at = datetime.now(timezone.utc)
    sr.save()
    return redirect("qc_review:event_detail_run",
                    public_id=sr.run.event.public_id,
                    run_number=sr.run.run_number)
