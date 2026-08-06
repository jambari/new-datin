# almanac/views.py
from django.shortcuts import render
from django.core.paginator import Paginator
from django.utils.dateparse import parse_date
from django.contrib.auth.decorators import login_required
from almanac.models import SunMoonEvent
from django.conf import settings
from datetime import datetime, date
import calendar
from django.db.models import Prefetch


def eventmoon_list(request):
    qs = SunMoonEvent.objects.all().order_by("date")

    # ---- Filter by city ----
    city = request.GET.get("city")
    if city:
        qs = qs.filter(city=city)

    # ---- Filter by date range ----
    start = parse_date(request.GET.get("start") or "")
    end   = parse_date(request.GET.get("end") or "")
    if start:
        qs = qs.filter(date__gte=start)
    if end:
        qs = qs.filter(date__lte=end)

    # ---- Pagination ----
    paginator = Paginator(qs, 31)  # 25 rows per page
    page_num  = request.GET.get("page")
    page_obj  = paginator.get_page(page_num)

    context = {
        "page_obj": page_obj,
        "city": city or "",
        "start": start,
        "end": end,
        "cities": [c["name"] for c in settings.SUNMOON_CITIES],
    }
    return render(request, "almanac/eventmoon_list.html", context)

@login_required
def sunmoon_monthly_report(request):
    """
    Laporan Bulanan Terbit/Terbenam Matahari & Bulan.
    Dikelompokkan per Kota; mendukung filter date range/kota dan kolom fase bulan.
    """
    today = datetime.now()
    date_from = request.GET.get('date_from', '')
    date_to   = request.GET.get('date_to', '')

    # Default: bulan ini (dari tgl 1 sampai hari ini)
    if not date_from:
        date_from = today.replace(day=1).strftime('%Y-%m-%d')
    if not date_to:
        date_to = today.strftime('%Y-%m-%d')

    try:
        dt_from = datetime.strptime(date_from, '%Y-%m-%d')
        dt_to   = datetime.strptime(date_to, '%Y-%m-%d')
    except ValueError:
        dt_from = today.replace(day=1)
        dt_to   = today
        date_from = dt_from.strftime('%Y-%m-%d')
        date_to   = dt_to.strftime('%Y-%m-%d')

    selected_city = request.GET.get('city', '')

    daftar_bulan_indo = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
                         "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    month_name = daftar_bulan_indo[dt_from.month]

    if hasattr(settings, 'SUNMOON_CITIES'):
        city_names = [c['name'] for c in settings.SUNMOON_CITIES]
    else:
        city_names = list(SunMoonEvent.objects.values_list('city', flat=True).distinct().order_by('city'))

    events_qs = SunMoonEvent.objects.filter(
        date__gte=dt_from,
        date__lte=dt_to,
    ).order_by('date')

    if selected_city and selected_city in city_names:
        filter_cities = [selected_city]
    else:
        filter_cities = city_names
        selected_city = ''

    report_data = []
    for city in filter_cities:
        city_events = events_qs.filter(city=city)
        if city_events.exists():
            report_data.append({'city': city, 'events': city_events})

    context = {
        'report_data':   report_data,
        'date_from':     date_from,
        'date_to':       date_to,
        'selected_city': selected_city,
        'month_name':    month_name,
        'city_names':    city_names,
        'page_title':    f"Jadwal Terbit Terbenam Matahari & Bulan ({date_from} s.d {date_to})",
    }

    return render(request, 'almanac/sunmoon_report.html', context)


def public_ttm(request):
    today = datetime.now()
    date_from = request.GET.get('date_from', '')
    date_to   = request.GET.get('date_to', '')

    if not date_from:
        date_from = today.replace(day=1).strftime('%Y-%m-%d')
    if not date_to:
        date_to = today.strftime('%Y-%m-%d')

    try:
        dt_from = datetime.strptime(date_from, '%Y-%m-%d')
        dt_to   = datetime.strptime(date_to, '%Y-%m-%d')
    except ValueError:
        dt_from = today.replace(day=1)
        dt_to   = today
        date_from = dt_from.strftime('%Y-%m-%d')
        date_to   = dt_to.strftime('%Y-%m-%d')

    selected_city = request.GET.get('city', '')

    daftar_bulan_indo = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
                         "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    month_name = daftar_bulan_indo[dt_from.month]

    if hasattr(settings, 'SUNMOON_CITIES'):
        city_names = [c['name'] for c in settings.SUNMOON_CITIES]
    else:
        city_names = list(SunMoonEvent.objects.values_list('city', flat=True).distinct().order_by('city'))

    events_qs = SunMoonEvent.objects.filter(
        date__gte=dt_from,
        date__lte=dt_to,
    ).order_by('date')

    if selected_city and selected_city in city_names:
        filter_cities = [selected_city]
    else:
        filter_cities = city_names
        selected_city = ''

    report_data = []
    for city in filter_cities:
        city_events = events_qs.filter(city=city)
        if city_events.exists():
            report_data.append({'city': city, 'events': city_events})

    context = {
        'report_data':    report_data,
        'date_from':      date_from,
        'date_to':        date_to,
        'selected_city':  selected_city,
        'month_name':     month_name,
        'city_names':     city_names,
        'page_title':     f"Terbit & Terbenam Matahari dan Bulan ({date_from} s.d {date_to})",
    }
    return render(request, 'almanac/public_ttm.html', context)
