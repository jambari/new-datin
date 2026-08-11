from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django_otp import devices_for_user, match_token
from django.conf import settings
from django.utils import timezone
from django.db.models import Sum, Max, Count
from django.views.decorators.cache import never_cache
from django.core.cache import cache
import datetime


@never_cache
@login_required
def dashboard(request):
    today = timezone.now().date()
    week_ago  = today - datetime.timedelta(days=7)
    month_ago = today - datetime.timedelta(days=30)

    # Per-user cache (30s) — avoids redundant queries on rapid redirects after login
    _cache_key = f"dash_ctx_{request.user.id}_{today.isoformat()}"
    _cached = cache.get(_cache_key)
    if _cached is not None:
        return render(request, 'dashboard.html', _cached)

    # --- Gempa stats (from EventBrowser — QuakeLink-sourced) ---
    from repository.models import EventBrowser, FeltEarthquake, GempaMemusak
    gempa_7d    = EventBrowser.objects.filter(origin_time__date__gte=week_ago).count()
    gempa_30d   = EventBrowser.objects.filter(origin_time__date__gte=month_ago).count()
    gempa_total = EventBrowser.objects.count()
    latest_gempa = EventBrowser.objects.order_by('-origin_time').first()
    felt_30d = FeltEarthquake.objects.filter(event_datetime__date__gte=month_ago).count()
    recent_felt = FeltEarthquake.objects.order_by('-event_datetime')[:5]

    # --- Terbit Terbenam Matahari (Jayapura) — show tomorrow ---
    from almanac.models import SunMoonEvent
    import zoneinfo as _zi
    _WIT = _zi.ZoneInfo("Asia/Jayapura")
    tomorrow_date = today + datetime.timedelta(days=1)
    sunmoon_tomorrow = SunMoonEvent.objects.filter(date=tomorrow_date, city='Jayapura').first()
    sun_rise_wit = sunmoon_tomorrow.sun_rise.astimezone(_WIT).strftime('%H:%M') if sunmoon_tomorrow and sunmoon_tomorrow.sun_rise else None
    sun_set_wit  = sunmoon_tomorrow.sun_set.astimezone(_WIT).strftime('%H:%M')  if sunmoon_tomorrow and sunmoon_tomorrow.sun_set  else None

    # --- Birthday today (WIT) from NIP YYYYMMDD prefix ---
    from jadwal.models import Pegawai
    now_wit_dt = timezone.now().astimezone(_WIT)
    today_wit_date = now_wit_dt.date()
    mmdd = today_wit_date.strftime('%m%d')
    _birthday_raw = list(
        Pegawai.objects.filter(nip__regex=r'^\d{4}' + mmdd)
        .order_by('urutan', 'nama')
    )
    birthday_pegawai = []
    for p in _birthday_raw:
        try:
            birth_year = int(p.nip[:4])
            age = today_wit_date.year - birth_year
        except (ValueError, TypeError):
            age = None
        birthday_pegawai.append({'nama': p.nama, 'umur': age})

    # --- Lapbul bulan ini ---
    from jadwal.models import Lapbul
    now_month = today_wit_date.month
    now_year  = today_wit_date.year
    lapbul_bulan_ini = Lapbul.objects.filter(bulan=now_month, tahun=now_year).order_by('-tahun', '-bulan').first()

    # --- Buletin deadline (bulan sebelumnya, deadline tgl 15 bulan ini) ---
    from repository.models import Bulletin
    BULAN_NAMA = ['','Januari','Februari','Maret','April','Mei','Juni','Juli','Agustus','September','Oktober','November','Desember']
    prev_month = now_month - 1 if now_month > 1 else 12
    prev_year  = now_year if now_month > 1 else now_year - 1
    buletin_deadline = {
        'bulan_label': BULAN_NAMA[prev_month],
        'tahun': prev_year,
        'deadline_label': '15 ' + BULAN_NAMA[now_month] + ' ' + str(now_year),
    }
    # Cek apakah buletin bulan sebelumnya (yg jadi deadline) sudah ada
    bulletin_ada = Bulletin.objects.filter(bulan=str(prev_month), tahun=str(prev_year)).exists()

    # --- WRSNG: removed for performance ---
    wrsng_statuses = []
    wrsng_online = 0

    # --- Logbook: last 5 entries ---
    from logbook.models import Logbook
    recent_logbook = Logbook.objects.order_by('-tanggal', '-waktu_dibuat')[:5]

    # --- Daily reminders ---
    from jadwal.models import JadwalHVSampler
    import zoneinfo
    now_wit = timezone.now().astimezone(zoneinfo.ZoneInfo("Asia/Jayapura"))
    today_wit = now_wit.date()
    dow = today_wit.weekday()  # 0=Mon,1=Tue,2=Wed,3=Thu,4=Fri,5=Sat,6=Sun

    hv_sampler_today = JadwalHVSampler.objects.filter(tanggal=today_wit).first()
    reminders = []
    if hv_sampler_today:
        reminders.append({
            'label': hv_sampler_today.get_tipe_display(),
            'color': '#f59e0b',
            'text': '#fff',
        })
    if dow in (2, 4):  # Rabu, Jumat
        reminders.append({'label': 'Pengamatan Absolut 09:00', 'color': '#7c3aed', 'text': '#fff'})
    if dow == 0:       # Senin
        reminders.append({'label': 'Ambil Sampel Hujan 09:00', 'color': '#0369a1', 'text': '#fff'})
    if dow in (0, 3):  # Senin, Kamis
        reminders.append({'label': 'Buat Prekursor 09:00',     'color': '#0891b2', 'text': '#fff'})
    if dow == 4:       # Jumat
        reminders.append({'label': 'Buat Infografis',          'color': '#059669', 'text': '#fff'})

    # --- Next shift from jadwal ---
    from jadwal.models import JadwalHarian
    from collections import defaultdict
    tomorrow = today + datetime.timedelta(days=1)
    day_after = today + datetime.timedelta(days=2)
    # Start from tomorrow — today is already shown in Logbook terkini
    next_shift_date = None
    next_shift_by_pola = []
    for check_date in [tomorrow, day_after]:
        schedules = (
            JadwalHarian.objects
            .filter(tanggal=check_date, pola__isnull=False, pola__is_libur=False)
            .select_related('pegawai', 'pola')
            .order_by('pola__jam_mulai', 'pegawai__urutan')
        )
        if schedules.exists():
            next_shift_date = check_date
            grouped = defaultdict(list)
            for s in schedules:
                grouped[s.pola].append(s.pegawai.nama)
            next_shift_by_pola = [
                {'pola': pola, 'names': names}
                for pola, names in sorted(grouped.items(), key=lambda x: x[0].jam_mulai)
            ]
            break

    # --- Latest QC events ---
    from qc_review.models import Event as QCEvent
    _qc_qs = QCEvent.objects.prefetch_related("runs__station_results").order_by("-origin_time")[:5]
    latest_qc_rows = [{"event": e, "summary": e.qc_summary} for e in _qc_qs]

    context = {
        'gempa_7d':            gempa_7d,
        'gempa_30d':           gempa_30d,
        'gempa_total':         gempa_total,
        'latest_gempa':        latest_gempa,
        'felt_30d':            felt_30d,
        'recent_felt':         recent_felt,
        'wrsng_statuses':      wrsng_statuses,
        'wrsng_online':        wrsng_online,
        'wrsng_total':         len(wrsng_statuses),
        'recent_logbook':      recent_logbook,
        'next_shift_date':     next_shift_date,
        'next_shift_by_pola':  next_shift_by_pola,
        'reminders':           reminders,
        'gempa_merusak_total': GempaMemusak.objects.count(),
        'sun_rise_wit':        sun_rise_wit,
        'sun_set_wit':         sun_set_wit,
        'sun_date':            tomorrow_date,
        'birthday_pegawai':    birthday_pegawai,
        'lapbul_bulan_ini':    lapbul_bulan_ini,
        'buletin_deadline':    buletin_deadline,
        'bulletin_ada':        bulletin_ada,
        'latest_qc_rows':      latest_qc_rows,
    }
    cache.set(_cache_key, context, 120)  # cache for 120 seconds
    return render(request, 'dashboard.html', context)


def _build_album_cover(albums):
    """Attach cover_url and cover_is_video to each album queryset item."""
    media = settings.MEDIA_URL
    for a in albums:
        cp = a.cover_photo
        if cp and cp.thumbnail_path:
            a.cover_url = media + cp.thumbnail_path
            a.cover_is_video = cp.is_video
        elif cp and not cp.is_video:
            a.cover_url = media + cp.file_path
            a.cover_is_video = False
        else:
            a.cover_url = ''
            a.cover_is_video = cp.is_video if cp else False
    return albums


def _parse_bmkg_dt(dt_str):
    """Parse BMKG datetime string like '202605060000' → '06 Mei, 00:00 WIT'."""
    try:
        from datetime import datetime as _dt
        s = str(dt_str)
        d = _dt.strptime(s[:12], '%Y%m%d%H%M')
        months = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des']
        return f"{d.day:02d} {months[d.month-1]}, {d.hour:02d}:00 WIT"
    except Exception:
        return str(dt_str)


def landing(request):
    import json
    from arsip.models import Album
    from qc_review.models import Event as QCEvent
    from repository.models import FeltEarthquake, ShakemapEvent
    albums = list(_build_album_cover(
        Album.objects.select_related('cover_photo')
        .annotate(foto_count=Count('fotos'))
        .order_by('-created_at')[:6]
    ))
    cutoff = timezone.now() - datetime.timedelta(days=30)
    events_qs = QCEvent.objects.filter(
        origin_time__gte=cutoff
    ).order_by('-origin_time').values(
        'public_id', 'latitude', 'longitude', 'magnitude',
        'depth_km', 'region', 'origin_time',
    )
    events_json = json.dumps([
        {
            'id':    e['public_id'],
            'lat':   e['latitude'],
            'lng':   e['longitude'],
            'mag':   round(e['magnitude'], 1) if e['magnitude'] is not None else 0,
            'depth': round(e['depth_km'], 1),
            'loc':   e['region'] or '',
            'time':  e['origin_time'].strftime('%Y-%m-%d %H:%M UTC'),
        }
        for e in events_qs
    ])
    felt_count = FeltEarthquake.objects.filter(event_datetime__gte=cutoff).count()
    latest_felt = FeltEarthquake.objects.order_by('-event_datetime').first()
    latest_shakemap = ShakemapEvent.objects.filter(
        magnitude__gt=0,
        shakemap_image__isnull=False,
    ).order_by('-event_time').first()

    return render(request, 'landing.html', {
        'albums': albums,
        'events_json': events_json,
        'felt_count': felt_count,
        'latest_felt': latest_felt,
        'latest_shakemap': latest_shakemap,
    })


def public_shakemap_list(request):
    from repository.models import FeltEarthquake
    from django.core.paginator import Paginator
    qs = FeltEarthquake.objects.order_by('-event_datetime')
    paginator = Paginator(qs, 15)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'public_shakemap_list.html', {
        'shakemap_list': page_obj.object_list,
        'page_obj': page_obj,
        'record_count': paginator.count,
    })


def public_spectra_list(request):
    """List events that have response-spectrum data (one card per FeltEarthquake)."""
    from repository.models import FeltEarthquake, EventResponseSpectrum
    from django.core.paginator import Paginator
    from django.db.models import Count
    from datetime import datetime, timezone as dt_timezone, timedelta

    _WIB = dt_timezone(timedelta(hours=7))

    # Each EventResponseSpectrum.event_id is a WIB-formatted timestamp.
    # Convert distinct event_ids back to UTC datetimes and count rows per event.
    counts_by_wib = dict(
        EventResponseSpectrum.objects
        .values_list('event_id')
        .annotate(n=Count('id'))
        .values_list('event_id', 'n')
    )

    utc_times = []
    counts_by_utc = {}
    for wib_ts, n in counts_by_wib.items():
        try:
            dt_wib = datetime.strptime(wib_ts, "%Y%m%d%H%M%S").replace(tzinfo=_WIB)
        except ValueError:
            continue
        dt_utc = dt_wib.astimezone(dt_timezone.utc)
        utc_times.append(dt_utc)
        counts_by_utc[dt_utc] = n

    qs = (
        FeltEarthquake.objects
        .filter(event_datetime__in=utc_times)
        .order_by('-event_datetime')
    )
    paginator = Paginator(qs, 15)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    items = [
        {'event': e, 'station_components': counts_by_utc.get(e.event_datetime, 0)}
        for e in page_obj.object_list
    ]
    return render(request, 'public_spectra_list.html', {
        'items': items,
        'page_obj': page_obj,
        'record_count': paginator.count,
    })


def _resolve_shakemap_context(pk):
    from repository.models import FeltEarthquake, ShakemapEvent, EventStationWaveform
    from django.shortcuts import get_object_or_404
    from datetime import timezone as dt_timezone, timedelta
    obj = get_object_or_404(FeltEarthquake, pk=pk)
    _WIB = dt_timezone(timedelta(hours=7))
    wib_ts = obj.event_datetime.astimezone(_WIB).strftime("%Y%m%d%H%M%S")
    shk_event = ShakemapEvent.objects.filter(event_id=wib_ts).first()
    # Check if this event has downloadable .mseed files (try both WIB and UTC formats)
    utc_ts  = obj.event_datetime.strftime("%Y%m%d%H%M%S")
    mseed_count = EventStationWaveform.objects.filter(
        event_id__in=[wib_ts, utc_ts]
    ).exclude(
        mseed__isnull=True
    ).exclude(
        mseed=''
    ).count()
    # Determine which event_id format has the mseed data
    mseed_event_id = None
    for eid in [wib_ts, utc_ts]:
        if EventStationWaveform.objects.filter(event_id=eid).exclude(mseed__isnull=True).exclude(mseed='').exists():
            mseed_event_id = eid
            break
    return {
        'object': obj,
        'shk_event': shk_event,
        'wib_ts': wib_ts,
        'has_mseed': mseed_count > 0,
        'mseed_count': mseed_count,
        'mseed_zip_url': f'/api/shakemap/{mseed_event_id}/mseed-zip/' if mseed_count > 0 else None,
    }


def public_shakemap_detail(request, pk):
    return render(request, 'public_shakemap_detail.html', _resolve_shakemap_context(pk))


def public_shakemap_spectrum(request, pk):
    return render(request, 'public_shakemap_spectrum.html', _resolve_shakemap_context(pk))


def public_gempa_detail(request, public_id):
    import json as _json
    from qc_review.models import Event as QCEvent, QCRun
    from django.shortcuts import get_object_or_404
    event = get_object_or_404(QCEvent, public_id=public_id)
    run = event.latest_run
    stations = list(run.station_results.all()) if run else []
    all_runs = event.runs.all()
    has_station_coords = any(
        s.station_lat is not None and s.station_lon is not None
        for s in stations
    )
    comparison = []
    for s in stations:
        def _fmt(dt):
            return dt.strftime("%H:%M:%S.%f")[:-4] if dt else None
        comparison.append({
            "code":            f"{s.network}.{s.station}",
            "distance_deg":    s.distance_deg,
            "distance_class":  s.distance_class,
            "qc_flag":         s.qc_flag,
            "analyst_p":       _fmt(s.analyst_p),
            "analyst_s":       _fmt(s.analyst_s),
            "auto_p":          _fmt(s.auto_p),
            "auto_s":          _fmt(s.auto_s),
            "auto_p_prob":     round(s.auto_p_prob, 3) if s.auto_p_prob is not None else None,
            "auto_s_prob":     round(s.auto_s_prob, 3) if s.auto_s_prob is not None else None,
            "delta_p":         round(s.delta_p, 3) if s.delta_p is not None else None,
            "delta_s":         round(s.delta_s, 3) if s.delta_s is not None else None,
            "filter_band":     f"{s.filter_freqmin:.1f}–{s.filter_freqmax:.1f} Hz",
            "reviewer_action": s.reviewer_action,
        })
    return render(request, 'qc_review/event_detail.html', {
        'event':             event,
        'run':               run,
        'stations':          stations,
        'summary':           run.qc_summary if run else {},
        'all_runs':          all_runs,
        'has_station_coords': has_station_coords,
        'comparison_json':   _json.dumps(comparison),
        'on_duty':           [],
        'on_duty_qc':        [],
        'is_public':         True,
    })


def public_gempa_merusak(request):
    import json
    from repository.models import GempaMemusak
    from django.db.models import F, Q
    from django.core.paginator import Paginator
    qs = GempaMemusak.objects.all().order_by(F('tanggal').desc(nulls_last=True), '-no')
    q        = request.GET.get('q', '').strip()
    provinsi = request.GET.get('provinsi', '').strip()
    tsunami  = request.GET.get('tsunami', '').strip()
    if q:
        qs = qs.filter(Q(tanggal_text__icontains=q) | Q(wilayah__icontains=q) | Q(korban_kerusakan__icontains=q))
    if provinsi:
        qs = qs.filter(provinsi=provinsi)
    if tsunami == '1':
        qs = qs.filter(tsunami=True)
    elif tsunami == '0':
        qs = qs.filter(tsunami=False)
    total_count = qs.count()
    # Map data uses ALL matching events (not just current page)
    events = list(qs.values(
        'no', 'tanggal_text', 'tanggal', 'wilayah', 'provinsi',
        'latitude', 'longitude', 'depth_km', 'magnitude',
        'lokasi', 'tsunami', 'korban_kerusakan',
    ))
    map_data = json.dumps([
        {
            'no':  e['no'],
            'lat': e['latitude'],
            'lng': e['longitude'],
            'mag': e['magnitude'],
            'loc': e['wilayah'],
            'tgl': e['tanggal_text'],
            'tsunami': e['tsunami'],
            'prov': e['provinsi'],
        }
        for e in events
        if e['latitude'] and e['longitude']
    ])
    paginator   = Paginator(qs, 10)
    page_obj    = paginator.get_page(request.GET.get('page'))
    return render(request, 'public_gempa_merusak.html', {
        'object_list':      page_obj,
        'page_obj':         page_obj,
        'total_count':      total_count,
        'map_data':         map_data,
        'province_choices': GempaMemusak.PROVINCE_CHOICES,
        'filter_q':         q,
        'filter_provinsi':  provinsi,
        'filter_tsunami':   tsunami,
    })


def gempa_public(request):
    import json
    from qc_review.models import Event as QCEvent
    from repository.models import FeltEarthquake
    from django.core.paginator import Paginator

    today = timezone.now().date()
    end_str   = request.GET.get('end')
    start_str = request.GET.get('start')
    try:
        end_date   = datetime.date.fromisoformat(end_str)   if end_str   else today
        start_date = datetime.date.fromisoformat(start_str) if start_str else today - datetime.timedelta(days=30)
    except ValueError:
        end_date   = today
        start_date = today - datetime.timedelta(days=30)

    if end_date > today:
        end_date = today
    if (end_date - start_date).days > 30:
        start_date = end_date - datetime.timedelta(days=30)
    if start_date > end_date:
        start_date = end_date - datetime.timedelta(days=30)

    qs = QCEvent.objects.filter(
        origin_time__date__gte=start_date,
        origin_time__date__lte=end_date,
    ).order_by('-origin_time')
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    all_events = list(qs.values(
        'public_id', 'latitude', 'longitude', 'magnitude', 'depth_km', 'region', 'origin_time'
    ))
    events_json = json.dumps([
        {
            'id':    e['public_id'],
            'lat':   e['latitude'],
            'lng':   e['longitude'],
            'mag':   round(e['magnitude'], 1) if e['magnitude'] is not None else 0,
            'depth': round(e['depth_km'], 1),
            'loc':   e['region'] or '',
            'time':  e['origin_time'].strftime('%Y-%m-%d %H:%M UTC'),
        }
        for e in all_events
    ])

    felt_qs = FeltEarthquake.objects.filter(
        event_datetime__date__gte=start_date,
        event_datetime__date__lte=end_date,
    ).values('latitude', 'longitude', 'magnitude', 'depth_km', 'wilayah', 'dirasakan', 'event_datetime')
    felt_json = json.dumps([
        {
            'lat':       f['latitude'],
            'lng':       f['longitude'],
            'mag':       round(f['magnitude'], 1),
            'depth':     round(f['depth_km'], 1),
            'wilayah':   f['wilayah'],
            'dirasakan': f['dirasakan'] or '',
            'time':      f['event_datetime'].strftime('%Y-%m-%d %H:%M UTC'),
        }
        for f in felt_qs
    ])

    return render(request, 'gempa_public.html', {
        'page_obj':    page_obj,
        'start_date':  start_date,
        'end_date':    end_date,
        'events_json': events_json,
        'felt_json':   felt_json,
    })


def our_work(request):
    from arsip.models import Album
    albums = list(_build_album_cover(
        Album.objects.select_related('cover_photo')
        .annotate(foto_count=Count('fotos'))
        .order_by('-created_at')
    ))
    return render(request, 'our_work.html', {'albums': albums})


def public_magnetbumi(request):
    return render(request, 'public_magnetbumi.html')


def public_magnetbumi_data(request):
    from django.http import JsonResponse
    from magnet.models import MagneticObservation

    today = timezone.now().date()
    end_str   = request.GET.get('end')
    start_str = request.GET.get('start')
    try:
        end_date   = datetime.date.fromisoformat(end_str)   if end_str   else today
        start_date = datetime.date.fromisoformat(start_str) if start_str else today - datetime.timedelta(days=30)
    except ValueError:
        end_date   = today
        start_date = today - datetime.timedelta(days=30)

    if (end_date - start_date).days > 30:
        start_date = end_date - datetime.timedelta(days=30)

    qs = (
        MagneticObservation.objects
        .filter(observation_date__range=[start_date, end_date])
        .exclude(declination=None)
        .order_by('observation_date', 'session')
        .values(
            'observation_date', 'session',
            'declination', 'inclination', 'total_intensity',
            'horizontal_intensity', 'vertical_intensity',
            'north_component', 'east_component',
        )
    )

    rows = []
    for r in qs:
        rows.append({
            'date':    r['observation_date'].strftime('%d/%m'),
            'session': r['session'],
            'D': float(r['declination'])          if r['declination']          is not None else None,
            'I': float(r['inclination'])          if r['inclination']          is not None else None,
            'F': float(r['total_intensity'])      if r['total_intensity']      is not None else None,
            'H': float(r['horizontal_intensity']) if r['horizontal_intensity'] is not None else None,
            'Z': float(r['vertical_intensity'])   if r['vertical_intensity']   is not None else None,
            'X': float(r['north_component'])      if r['north_component']      is not None else None,
            'Y': float(r['east_component'])       if r['east_component']       is not None else None,
        })

    return JsonResponse({'rows': rows})


def public_petir(request):
    return render(request, 'public_petir.html')


def public_petir_data(request):
    import json
    from django.http import JsonResponse
    from lightning.models import DailyStrikeSummary
    from hujan.models import Hujan

    end_str   = request.GET.get('end')
    start_str = request.GET.get('start')

    today = timezone.now().date()
    try:
        end_date   = datetime.date.fromisoformat(end_str)   if end_str   else today
        start_date = datetime.date.fromisoformat(start_str) if start_str else today - datetime.timedelta(days=6)
    except ValueError:
        end_date   = today
        start_date = today - datetime.timedelta(days=6)

    # Clamp to max 30 days
    if (end_date - start_date).days > 30:
        start_date = end_date - datetime.timedelta(days=30)

    lightning_map = {
        s.summary_date: s
        for s in DailyStrikeSummary.objects.filter(summary_date__range=[start_date, end_date])
    }
    rain_map = {
        h.tanggal: h.obs
        for h in Hujan.objects.filter(tanggal__range=[start_date, end_date])
    }

    labels, petir, hujan, cg_plus, cg_minus = [], [], [], [], []
    d = start_date
    while d <= end_date:
        labels.append(d.strftime('%d/%m'))
        s = lightning_map.get(d)
        petir.append(s.total_count    if s else 0)
        cg_plus.append(s.cg_plus_count  if s else 0)
        cg_minus.append(s.cg_minus_count if s else 0)
        hujan.append(float(rain_map.get(d, 0)))
        d += datetime.timedelta(days=1)

    return JsonResponse({'labels': labels, 'petir': petir, 'hujan': hujan,
                         'cg_plus': cg_plus, 'cg_minus': cg_minus})


def public_about(request):
    from repository.models import AcceleroDataAvailability
    # Seismic station count is a fixed infrastructure fact (27 BMKG-managed sites).
    # DataAvailability also stores stations from external networks and pseudo-channels
    # (REPORT, SLINKTOOL), so a raw DB count overstates the real number.
    seismo_count = 26
    accelero_count = AcceleroDataAvailability.objects.values('station').distinct().count()
    return render(request, 'public_about.html', {
        'seismo_count': seismo_count,
        'accelero_count': accelero_count,
    })


def public_glosarium(request):
    return render(request, 'public_glosarium.html')


def poster_datin(request):
    return render(request, 'poster_datin.html')


def public_peringatan_dini_data(request):
    import requests as http_req
    from xml.etree import ElementTree as ET
    from django.http import JsonResponse
    from django.core.cache import cache
    from email.utils import parsedate_to_datetime
    import datetime as dt_

    cached = cache.get('peringatan_dini_papua')
    if cached is not None:
        return JsonResponse({'items': cached})

    try:
        resp = http_req.get('https://www.bmkg.go.id/alerts/nowcast/id', timeout=6)
        root = ET.fromstring(resp.content)
        channel = root.find('channel')
        cutoff = dt_.datetime.now(dt_.timezone.utc) - dt_.timedelta(hours=4)

        items = []
        for item in (channel.findall('item') if channel is not None else []):
            title = item.findtext('title', '')
            if 'Papua' not in title:
                continue
            pub = item.findtext('pubDate', '')
            try:
                pub_dt = parsedate_to_datetime(pub)
                if pub_dt < cutoff:
                    continue
                pub_iso = pub_dt.isoformat()
            except Exception:
                pub_iso = pub

            event    = title.split(' di ')[0] if ' di ' in title else title
            province = title.split(' di ', 1)[-1] if ' di ' in title else ''
            desc     = item.findtext('description', '')
            link     = item.findtext('link', '')

            items.append({
                'event': event, 'province': province,
                'desc': desc, 'pubDate': pub_iso, 'link': link,
            })

        cache.set('peringatan_dini_papua', items, 180)
        return JsonResponse({'items': items})
    except Exception as e:
        return JsonResponse({'items': [], 'error': str(e)})


# ── Bulletin / Buletin ──────────────────────────────────────────────────


from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
from repository.models import Bulletin, SiaranPress


def public_bulletin_list(request):
    """Daftar semua buletin."""
    bulletins = Bulletin.objects.all()
    tahun_list = bulletins.values_list('tahun', flat=True).distinct().order_by('-tahun')

    tahun = request.GET.get('tahun', '')
    if tahun:
        bulletins = bulletins.filter(tahun=tahun)

    paginator = Paginator(bulletins, 12)
    page = request.GET.get('page', 1)
    bulletins_page = paginator.get_page(page)

    return render(request, 'bulletins/list.html', {
        'bulletins': bulletins_page,
        'tahun_list': tahun_list,
        'selected_tahun': tahun,
    })


def public_bulletin_detail(request, pk):
    """Detail buletin."""
    bulletin = get_object_or_404(Bulletin, pk=pk)
    latest = Bulletin.objects.exclude(pk=pk).order_by('-tahun', '-bulan')[:5]
    return render(request, 'bulletins/detail.html', {
        'bulletin': bulletin,
        'latest': latest,
    })


def public_siaranpress_list(request):
    """Daftar siaran press."""
    siarans = SiaranPress.objects.all()
    paginator = Paginator(siarans, 10)
    page = request.GET.get('page', 1)
    siarans_page = paginator.get_page(page)
    return render(request, 'siaranpress/list.html', {
        'siarans': siarans_page,
    })


def public_siaranpress_detail(request, pk):
    """Detail siaran press."""
    siaran = get_object_or_404(SiaranPress, pk=pk)
    latest = SiaranPress.objects.exclude(pk=pk).order_by('-created_at')[:5]
    return render(request, 'siaranpress/detail.html', {
        'siaran': siaran,
        'latest': latest,
    })


# ── Account Profile ─────────────────────────────────────────

@login_required
def account_profile(request):
    from django.contrib.auth.forms import PasswordChangeForm
    from django_otp.plugins.otp_totp.models import TOTPDevice
    import qrcode, io, base64

    pw_form = PasswordChangeForm(user=request.user)
    pw_msg = None
    otp_msg = None

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'change_password':
            pw_form = PasswordChangeForm(user=request.user, data=request.POST)
            if pw_form.is_valid():
                pw_form.save()
                pw_msg = 'Password berhasil diubah.'
            else:
                pw_msg = 'Gagal mengubah password — periksa input.'

        elif action == 'setup_otp':
            device, created = TOTPDevice.objects.get_or_create(
                user=request.user, name='default',
                defaults={'confirmed': False},
            )
            device.save()
            otp_msg = 'OTP device siap. Scan QR code dengan Google Authenticator.'

        elif action == 'confirm_otp':
            token = request.POST.get('otp_token', '')
            device = TOTPDevice.objects.filter(user=request.user, name='default').first()
            if device and device.verify_token(token):
                device.confirmed = True
                device.save()
                otp_msg = 'OTP berhasil diaktifkan!'
            else:
                otp_msg = 'Kode OTP tidak valid.'

        elif action == 'disable_otp':
            TOTPDevice.objects.filter(user=request.user, name='default').delete()
            otp_msg = 'OTP dinonaktifkan.'

    # Get current OTP device
    otp_device = TOTPDevice.objects.filter(user=request.user, name='default', confirmed=True).first()
    otp_enabled = otp_device is not None

    # Generate QR code for setup
    qr_svg = None
    if not otp_enabled:
        unconfirmed = TOTPDevice.objects.filter(user=request.user, name='default', confirmed=False).first()
        if not unconfirmed:
            unconfirmed, _ = TOTPDevice.objects.get_or_create(
                user=request.user, name='default',
                defaults={'confirmed': False},
            )
        if unconfirmed:
            otp_url = unconfirmed.config_url
            qr_img = qrcode.make(otp_url)
            buf = io.BytesIO()
            qr_img.save(buf, format='PNG')
            qr_svg = base64.b64encode(buf.getvalue()).decode()

    return render(request, 'account.html', {
        'pw_form': pw_form,
        'pw_msg': pw_msg,
        'otp_msg': otp_msg,
        'otp_enabled': otp_enabled,
        'qr_svg': qr_svg,
    })


# ── Custom Login with OTP ───────────────────────────────────

def custom_login(request):
    from django.contrib.auth.forms import AuthenticationForm
    from django.contrib.auth import login as auth_login

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            next_url = request.POST.get('next') or request.GET.get('next', '')
            if next_url:
                return redirect(next_url)
            if devices_for_user(user):
                return redirect('otp_verify')
            return redirect('dashboard')
    else:
        form = AuthenticationForm(request)

    return render(request, 'registration/login.html', {
        'form': form,
        'next': request.GET.get('next', ''),
    })


def otp_verify(request):
    if not request.user.is_authenticated:
        return redirect('login')

    msg = None
    if request.method == 'POST':
        token = request.POST.get('otp_token', '')
        device = match_token(request.user, token)
        if device:
            request.user.otp_device = device
            return redirect('dashboard')
        else:
            msg = 'Kode OTP tidak valid. Coba lagi.'

    return render(request, 'otp_verify.html', {'msg': msg})
