from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Sum, Max
import datetime


@login_required
def dashboard(request):
    today = timezone.now().date()
    week_ago  = today - datetime.timedelta(days=7)
    month_ago = today - datetime.timedelta(days=30)

    # --- Gempa stats ---
    from repository.models import Gempa, FeltEarthquake, GempaMemusak
    gempa_7d    = Gempa.objects.filter(origin_datetime__date__gte=week_ago).count()
    gempa_30d   = Gempa.objects.filter(origin_datetime__date__gte=month_ago).count()
    gempa_total = Gempa.objects.count()
    latest_gempa = Gempa.objects.order_by('-origin_datetime').first()
    felt_30d = FeltEarthquake.objects.filter(event_datetime__date__gte=month_ago).count()
    recent_felt = FeltEarthquake.objects.order_by('-event_datetime')[:5]

    # --- Terbit Terbenam Matahari (Jayapura) ---
    from almanac.models import SunMoonEvent
    import zoneinfo as _zi
    _WIT = _zi.ZoneInfo("Asia/Jayapura")
    sunmoon_today = SunMoonEvent.objects.filter(date=today, city='Jayapura').first()
    sun_rise_wit = sunmoon_today.sun_rise.astimezone(_WIT).strftime('%H:%M') if sunmoon_today and sunmoon_today.sun_rise else None
    sun_set_wit  = sunmoon_today.sun_set.astimezone(_WIT).strftime('%H:%M')  if sunmoon_today and sunmoon_today.sun_set  else None

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
    # Look for schedules today then tomorrow; pick the nearest date that has data
    next_shift_date = None
    next_shift_by_pola = []
    for check_date in [today, tomorrow]:
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
    }
    return render(request, 'dashboard.html', context)
