from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.utils import timezone
from django.db.models import Sum, Max, Count
import datetime


@login_required
def dashboard(request):
    today = timezone.now().date()
    week_ago  = today - datetime.timedelta(days=7)
    month_ago = today - datetime.timedelta(days=30)

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
    birthday_pegawai = list(
        Pegawai.objects.filter(nip__regex=r'^\d{4}' + mmdd)
        .order_by('urutan', 'nama')
    )

    # --- Lightning ---
    from lightning.models import DailyStrikeSummary
    lightning_7d = DailyStrikeSummary.objects.filter(summary_date__gte=week_ago).order_by('summary_date')
    yesterday = today - datetime.timedelta(days=1)
    lightning_yesterday = DailyStrikeSummary.objects.filter(summary_date=yesterday).first()
    lightning_today_count = lightning_yesterday.total_count if lightning_yesterday else 0

    # --- WRSNG: latest status per station ---
    from wrsng.models import WRSNGStatus
    from wrsng.constants import CODE_TO_STATION
    from django.db.models import Subquery, OuterRef
    latest_per_station = (
        WRSNGStatus.objects
        .filter(wrs_code=OuterRef('wrs_code'))
        .order_by('-status_datetime')
        .values('id')[:1]
    )
    wrsng_statuses_qs = (
        WRSNGStatus.objects
        .filter(id__in=Subquery(latest_per_station))
        .order_by('wrs_code')
    )
    wrsng_statuses = [
        {'name': CODE_TO_STATION.get(s.wrs_code, s.wrs_code), 'display_status': s.display_status}
        for s in wrsng_statuses_qs
    ]
    wrsng_online = sum(1 for s in wrsng_statuses if s['display_status'] == 1)

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

    # --- Lightning chart data (7 days) ---
    chart_labels = []
    chart_data   = []
    for i in range(6, -1, -1):
        d = today - datetime.timedelta(days=i)
        chart_labels.append(d.strftime('%d/%m'))
        summary = next((s for s in lightning_7d if s.summary_date == d), None)
        chart_data.append(summary.total_count if summary else 0)

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
        'lightning_today':     lightning_today_count,
        'wrsng_statuses':      wrsng_statuses,
        'wrsng_online':        wrsng_online,
        'wrsng_total':         len(wrsng_statuses),
        'recent_logbook':      recent_logbook,
        'next_shift_date':     next_shift_date,
        'next_shift_by_pola':  next_shift_by_pola,
        'reminders':           reminders,
        'chart_labels':        chart_labels,
        'chart_data':          chart_data,
        'gempa_merusak_total': GempaMemusak.objects.count(),
        'sun_rise_wit':        sun_rise_wit,
        'sun_set_wit':         sun_set_wit,
        'sun_date':            tomorrow_date,
        'birthday_pegawai':    birthday_pegawai,
        'latest_qc_rows':      latest_qc_rows,
    }
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


def landing(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    from arsip.models import Album
    albums = list(_build_album_cover(
        Album.objects.select_related('cover_photo')
        .annotate(foto_count=Count('fotos'))
        .order_by('-created_at')[:6]
    ))
    return render(request, 'landing.html', {'albums': albums})


def our_work(request):
    from arsip.models import Album
    albums = list(_build_album_cover(
        Album.objects.select_related('cover_photo')
        .annotate(foto_count=Count('fotos'))
        .order_by('-created_at')
    ))
    return render(request, 'our_work.html', {'albums': albums})
