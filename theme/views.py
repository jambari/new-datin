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

    # --- Lightning ---
    from lightning.models import DailyStrikeSummary
    lightning_7d = DailyStrikeSummary.objects.filter(summary_date__gte=week_ago).order_by('summary_date')
    lightning_today = DailyStrikeSummary.objects.filter(summary_date=today).first()
    lightning_today_count = lightning_today.total_count if lightning_today else 0

    # --- WRSNG: latest status per station ---
    from wrsng.models import WRSNGStatus
    from django.db.models import Subquery, OuterRef
    latest_per_station = (
        WRSNGStatus.objects
        .filter(wrs_code=OuterRef('wrs_code'))
        .order_by('-status_datetime')
        .values('id')[:1]
    )
    wrsng_statuses = (
        WRSNGStatus.objects
        .filter(id__in=Subquery(latest_per_station))
        .order_by('wrs_code')
    )
    wrsng_online = sum(1 for s in wrsng_statuses if s.display_status == 1)

    # --- Logbook: last 5 entries ---
    from logbook.models import Logbook
    recent_logbook = Logbook.objects.order_by('-tanggal', '-waktu_dibuat')[:5]

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
        'wrsng_total':         wrsng_statuses.count(),
        'recent_logbook':      recent_logbook,
        'chart_labels':        chart_labels,
        'chart_data':          chart_data,
        'gempa_merusak_total': GempaMemusak.objects.count(),
    }
    return render(request, 'dashboard.html', context)
