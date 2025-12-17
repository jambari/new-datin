# almanac/views.py
from django.shortcuts import render
from django.core.paginator import Paginator
from django.utils.dateparse import parse_date
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

def sunmoon_monthly_report(request):
    """
    Laporan Bulanan Terbit/Terbenam Matahari & Bulan.
    Dikelompokkan per Kota.
    """
    today = datetime.now()
    try:
        selected_month = int(request.GET.get('month', today.month))
        selected_year = int(request.GET.get('year', today.year))
    except ValueError:
        selected_month = today.month
        selected_year = today.year

    # Helper nama bulan
    daftar_bulan_indo = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    month_name = daftar_bulan_indo[selected_month]

    # Ambil Daftar Kota dari Settings (agar urutannya konsisten) atau DB
    # Asumsi settings.SUNMOON_CITIES ada, jika tidak ambil unique dari DB
    if hasattr(settings, 'SUNMOON_CITIES'):
        city_names = [c['name'] for c in settings.SUNMOON_CITIES]
    else:
        city_names = SunMoonEvent.objects.values_list('city', flat=True).distinct().order_by('city')

    # Query Semua Data Bulan Tersebut
    events_qs = SunMoonEvent.objects.filter(
        date__year=selected_year,
        date__month=selected_month
    ).order_by('date')

    # Grouping Data: { 'Nama Kota': [Event Tgl 1, Event Tgl 2, ...], ... }
    report_data = []
    
    for city in city_names:
        # Filter event untuk kota ini (dilakukan di python level atau query ulang, 
        # query ulang lebih simple kodenya meski hit db nambah dikit per kota)
        city_events = events_qs.filter(city=city)
        
        if city_events.exists():
            report_data.append({
                'city': city,
                'events': city_events
            })

    context = {
        'report_data': report_data,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'month_name': month_name,
        'years_range': range(2020, 2030),
        'months_range': range(1, 13),
        'page_title': f"Jadwal Terbit Terbenam Matahari & Bulan - {month_name} {selected_year}",
    }

    return render(request, 'almanac/sunmoon_report.html', context)
