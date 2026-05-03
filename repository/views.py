from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from .models import Gempa, DataAvailability
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from .models import Station
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import DataAvailabilitySerializer
from datetime import datetime
from .models import AcceleroDataAvailability
from .serializers import AcceleroDataAvailabilitySerializer
from rest_framework import generics
from .serializers import GempaSerializer
from django.http import HttpResponse
import csv
from .models import ShakemapEvent
from django.views import generic
from django.db.models import Avg
from collections import defaultdict
import json
from django.core.serializers.json import DjangoJSONEncoder
from datetime import date, timedelta, datetime, timezone as dt_timezone
from django.views.generic.edit import DeleteView
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
import calendar
from django.db.models import Prefetch
from django.utils import timezone
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from .models import JSONDataUpload, FeltEarthquake, GempaMemusak, GempaMemusakMedia
from .utils import calculate_remark
import json
from io import StringIO
import re
from dateutil import parser as dateutil_parser

def station_map_view(request):
    return render(request, 'repository/station_map.html')

@login_required
def gempa_list(request):
    queryset = Gempa.objects.all()
    station_codes = Gempa.objects.values_list('station_code', flat=True).distinct().order_by('station_code')
    
    # Get filter values from the request
    q = request.GET.get('q')
    felt = request.GET.get('felt')
    min_mag = request.GET.get('min_mag')
    max_mag = request.GET.get('max_mag')
    min_depth = request.GET.get('min_depth')
    max_depth = request.GET.get('max_depth')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    min_lat = request.GET.get('min_lat')
    max_lat = request.GET.get('max_lat')
    min_lon = request.GET.get('min_lon')
    max_lon = request.GET.get('max_lon')
    station = request.GET.get('station')

    # Apply filters
    if q:
        # Gunakan 'remark' dan 'impact' untuk pencarian
        queryset = queryset.filter(Q(remark__icontains=q) | Q(impact__icontains=q))
    if felt == 'true':
        queryset = queryset.filter(felt=True)
    elif felt == 'false':
        queryset = queryset.filter(felt=False)
    if min_mag:
        queryset = queryset.filter(magnitudo__gte=min_mag)
    if max_mag:
        queryset = queryset.filter(magnitudo__lte=max_mag)
    if min_depth:
        queryset = queryset.filter(depth__gte=min_depth)
    if max_depth:
        queryset = queryset.filter(depth__lte=max_depth)
    # CORRECT CODE
    if start_date:
        queryset = queryset.filter(origin_datetime__date__gte=start_date)
    if end_date:
        queryset = queryset.filter(origin_datetime__date__lte=end_date)
    if min_lat:
        queryset = queryset.filter(latitude__gte=min_lat)
    if max_lat:
        queryset = queryset.filter(latitude__lte=max_lat)
    if min_lon:
        queryset = queryset.filter(longitude__gte=min_lon)
    if max_lon:
        queryset = queryset.filter(longitude__lte=max_lon)
    if station:
        queryset = queryset.filter(station_code=station)

    # --- LOGIKA EKSPOR CSV BARU ---
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="gempas.csv"'
        
        writer = csv.writer(response)
        # Tulis baris header
        writer.writerow(['Longitude','Latitude','Magnitude', 'Depth','Date', 'Time (UTC)'])
        
        # Tulis baris data
        for gempa in queryset:
            writer.writerow([
                gempa.longitude,
                gempa.latitude,
                gempa.magnitudo,
                gempa.depth,
                gempa.origin_datetime.strftime('%Y-%m-%d'),
                gempa.origin_datetime.strftime('%H:%M:%S'),
            ])
            
        return response
    
    # Pagination
    paginator = Paginator(queryset, 25)
    page_number = request.GET.get('page')
    gempas = paginator.get_page(page_number)

    context = {
        'gempas': gempas,
        'filters': request.GET, # Pass all GET params to template
        'station_codes': station_codes, 
    }
    return render(request, 'repository/gempa_list.html', context)


@login_required
def gempa_detail_view(request, pk):
    gempa = get_object_or_404(Gempa, pk=pk)


    # --- Logika Baru untuk Latitude ---
    lat_val = gempa.latitude
    if lat_val < 0:
        lat_display = lat_val * -1  # Ambil nilai absolut (positif)
        lat_hemisphere = "LS" # Lintang Selatan
    else:
        lat_display = lat_val
        lat_hemisphere = "LU" # Lintang Utara


    gempa_data_for_js = {
        'lat': gempa.latitude,
        'lon': gempa.longitude,
        'mag': gempa.magnitudo,
        'depth': gempa.depth,
        'place': gempa.remark,
    }
    context = {
        'gempa': gempa,
        'gempa_data_for_js': gempa_data_for_js,
        'lat_display': lat_display,           # Kirim nilai latitude yang sudah diproses
        'lat_hemisphere': lat_hemisphere,
    }
    return render(request, 'repository/gempa_detail.html', context)


@login_required
def gempa_edit(request, pk):
    gempa = get_object_or_404(Gempa, pk=pk)
    if request.method == 'POST':
        gempa.station_code = request.POST.get('station_code', gempa.station_code)
        gempa.origin_datetime = request.POST.get('origin_datetime', gempa.origin_datetime)
        gempa.latitude = request.POST.get('latitude', gempa.latitude)
        gempa.longitude = request.POST.get('longitude', gempa.longitude)
        gempa.magnitudo = request.POST.get('magnitudo', gempa.magnitudo)
        gempa.depth = request.POST.get('depth', gempa.depth)
        gempa.remark = request.POST.get('remark', gempa.remark)
        gempa.felt = request.POST.get('felt') == 'true'
        gempa.impact = request.POST.get('impact', gempa.impact) or None
        gempa.save()
        return redirect('gempa_list')
    return render(request, 'repository/gempa_form.html', {'gempa': gempa})


@login_required
def gempa_delete(request, pk):
    gempa = get_object_or_404(Gempa, pk=pk)
    if request.method == 'POST':
        gempa.delete()
        return redirect('gempa_list')
    return render(request, 'repository/gempa_confirm_delete.html', {'gempa': gempa})


def station_geojson_api(request):
    """
    API view to provide station data in GeoJSON format.
    """
    features = []
    for station in Station.objects.all():
        features.append({
            "type": "Feature",
            "properties": {
                "code": station.code,
                "network": station.network,
                "name": station.name,
            },
            "geometry": {
                "type": "Point",
                "coordinates": [
                    station.longitude,
                    station.latitude,
                    station.elevation or 0
                ]
            }
        })

    geojson_data = {
        "type": "FeatureCollection",
        "features": features
    }
    
    return JsonResponse(geojson_data)


def station_search_api(request):
    """
    API view for station autocomplete search.
    """
    query = request.GET.get('q', '')
    stations_data = []
    if query:
        # 2. Ubah filter untuk mencari di field 'name' ATAU 'code'
        stations = Station.objects.filter(
            Q(name__icontains=query) | Q(code__icontains=query)
        )[:10]
        
        for station in stations:
            stations_data.append({
                'name': station.name,
                'code': station.code,
                'url': reverse('station_detail', args=[station.code])
            })
    return JsonResponse({'stations': stations_data})


def station_detail_view(request, station_code):
    station = get_object_or_404(Station, code=station_code)
    
    # Siapkan data untuk peta Leaflet di halaman detail
    station_data_for_js = {
        'lat': station.latitude,
        'lon': station.longitude,
        'name': station.name,
        'code': station.code,
    }

    context = {
        'station': station,
        'station_data_for_js': station_data_for_js
    }
    return render(request, 'repository/station_detail.html', context)

class DataAvailabilityReportView(APIView):
    """
    Menerima laporan ketersediaan data dari server internal SeisComP.
    """
    def post(self, request, format=None):
        serializer = DataAvailabilitySerializer(data=request.data, many=True)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"status": "success", "message": f"{len(serializer.data)} records saved."},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

def data_availability_list(request):
    # Handle bulk deletion
    if request.method == 'POST':
        selected_ids = request.POST.getlist('selected_records')
        if selected_ids:
            DataAvailability.objects.filter(id__in=selected_ids).delete()
            return redirect('data_availability_list')

    # Filtering logic
    station_code = request.GET.get('station_code')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    all_records = DataAvailability.objects.all()

    if station_code:
        all_records = all_records.filter(station__icontains=station_code)
    
    if start_date:
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            all_records = all_records.filter(date__gte=start_date_obj)
        except ValueError:
            pass

    if end_date:
        try:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            all_records = all_records.filter(date__lte=end_date_obj)
        except ValueError:
            pass

    all_records = all_records.order_by('-date')

    # Pagination
    paginator = Paginator(all_records, 25)
    page = request.GET.get('page')
    
    try:
        records = paginator.page(page)
    except PageNotAnInteger:
        records = paginator.page(1)
    except EmptyPage:
        records = paginator.page(paginator.num_pages)

    context = {
        'records': records,
        'station_code': station_code,
        'start_date': start_date,
        'end_date': end_date
    }
    return render(request, 'repository/data_availability_list.html', context)

class AcceleroDataAvailabilityView(APIView):
    """
    API endpoint to receive and save a list of accelerograph data availability records.
    """
    def post(self, request, *args, **kwargs):
        # A list of dictionaries is expected in the request data
        serializer = AcceleroDataAvailabilitySerializer(data=request.data, many=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

def accelero_availability_list(request):
    all_records = AcceleroDataAvailability.objects.all().order_by('-date')
    
    # Set the number of records per page
    paginator = Paginator(all_records, 25)
    
    # Get the current page number
    page = request.GET.get('page')
    
    try:
        records = paginator.page(page)
    except PageNotAnInteger:
        records = paginator.page(1)
    except EmptyPage:
        records = paginator.page(paginator.num_pages)

    context = {
        'records': records
    }
    return render(request, 'repository/accelero_availability_list.html', context)

class GempaCreateAPIView(generics.CreateAPIView):
    """
    API endpoint untuk membuat record Gempa baru.
    """
    queryset = Gempa.objects.all()
    serializer_class = GempaSerializer

class ShakemapListView(generic.ListView):
    model = FeltEarthquake
    context_object_name = 'shakemap_list'
    template_name = 'repository/shakemapevent_list.html'
    ordering = ['-event_datetime']
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['record_count'] = context['paginator'].count
        return context


class ShakemapDetailView(generic.DetailView):
    model = FeltEarthquake
    template_name = 'repository/shakemapevent_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        fe = self.object
        _WIB = dt_timezone(timedelta(hours=7))
        wib_ts = fe.event_datetime.astimezone(_WIB).strftime("%Y%m%d%H%M%S")
        context['shk_event'] = ShakemapEvent.objects.filter(event_id=wib_ts).first()
        return context

@login_required
def query_seismo_availability(request):
    """
    MODIFIKASI V3: 
    1. Default value jika data tidak ada = 0.
    2. Logika pengambilan data: Manual > Raw > Default(0).
    """
    # 1. Setup Waktu
    today = datetime.now()
    try:
        selected_month = int(request.GET.get('month', today.month))
        selected_year = int(request.GET.get('year', today.year))
    except ValueError:
        selected_month = today.month
        selected_year = today.year

    _, num_days = calendar.monthrange(selected_year, selected_month)
    list_tanggal = list(range(1, num_days + 1))
    
    daftar_bulan_indo = [
        "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember"
    ]
    
    # Ambil nama bulan berdasarkan index angka (1-12)
    month_name = daftar_bulan_indo[selected_month]

    # 2. Daftar Stasiun
    station_list = [
        'ARPI', 'ARKPI', 'BTSPI', 'DYPI', 'EDMPI', 'ELMPI', 'FKMPM', 'GENI', 'JAY', 'KIMPI', 
        'LJPI', 'MIBPI', 'MMPI', 'MTJPI', 'MTMPI', 'OBMPI', 'SATPI', 'SJPM', 'SKPM', 'SOMPI', 
        'SUSPI', 'TRPI', 'UWNPI', 'WAMI', 'WANPI', 'YBYPI'
    ]

    start_date = date(selected_year, selected_month, 1)
    end_date = date(selected_year, selected_month, num_days)

    # 3. Ambil Data
    # A. Data Manual (Report)
    manual_data_query = DataAvailability.objects.filter(
        station__in=station_list,
        date__range=[start_date, end_date],
        channel='REPORT'
    ).values('station', 'date', 'percentage')

    manual_map = {}
    for item in manual_data_query:
        key = (item['station'], item['date'].strftime('%Y-%m-%d'))
        manual_map[key] = item['percentage']

    # B. Data Raw (Mesin) - Rata-rata harian
    raw_data_query = DataAvailability.objects.filter(
        station__in=station_list,
        date__range=[start_date, end_date]
    ).exclude(
        channel='REPORT'
    ).values('station', 'date').annotate(avg_pct=Avg('percentage'))

    raw_map = {}
    for item in raw_data_query:
        key = (item['station'], item['date'].strftime('%Y-%m-%d'))
        raw_map[key] = item['avg_pct']

    # 4. Bangun Tabel
    tabel_data = []
    
    for stasiun in station_list:
        row = {
            'nama': stasiun,
            'hari': [],
            'avg_row': 0
        }
        total_val = 0
        
        for d in list_tanggal:
            curr_date = date(selected_year, selected_month, d)
            date_str = curr_date.strftime('%Y-%m-%d')
            key = (stasiun, date_str)
            
            val = 0.0 # Default Value sekarang 0
            
            if key in manual_map:
                val = manual_map[key]
            elif key in raw_map:
                val = raw_map[key]
            else:
                val = 0.0 # Pastikan default 0 jika tidak ada data
            
            val = float(val)

            row['hari'].append({
                'day_num': d,
                'full_date': date_str,
                'val': val
            })
            total_val += val
            
        row['avg_row'] = round(total_val / num_days, 2)
        tabel_data.append(row)

    context = {
        'tabel_data': tabel_data,
        'list_tanggal': list_tanggal,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'month_name': month_name,
        'years_range': range(2020, 2030),
        'months_range': range(1, 13),
    }

    return render(request, 'repository/data_availability_query.html', context)

class ShakemapEventDeleteView(DeleteView):
    model = FeltEarthquake
    template_name = 'repository/shakemapevent_confirm_delete.html'
    success_url = reverse_lazy('shakemap-list')

# Add this new view to your views.py

def query_accelero_availability(request):
    """
    Handles the query page for accelerograph data availability.
    Allows users to filter by a date range, calculates the daily average 
    availability across the NS, EW, and Z components, and displays the 
    results in a chart for each station.
    """
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    stations_data = None

    # IMPORTANT: Update this list with your actual accelerograph station codes
    stations_to_include = [
        'ARKPI', 'ARPI', 'BMPI', 'BTSPI', 'DYPI', 'EDMPI', 'ELMPI', 'FKMPM', 
        'GENI', 'JBPI', 'JGPI', 'JMPI', 'KIMPI', 'LJPI', 'MIBPI', 'MMPI', 'MTJPI', 'MTMPI', 'OBMPI', 'SATPI',
        'SKPM', 'SMPI', 'SOMPI', 'TMPI', 'TRPI', 'WAMI'
    ]

    if start_date_str and end_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

        # 1. Fetch data and calculate the daily average percentage for each station.
        #    The .annotate(Avg('percentage')) automatically groups by the fields
        #    in .values(), effectively averaging the NS, EW, and Z components for each day.
        results = (
            AcceleroDataAvailability.objects.filter(
                date__range=[start_date, end_date],
                station__in=stations_to_include
            )
            .values("date", "station")
            .annotate(average_percentage=Avg("percentage"))
            .order_by("date", "station")
        )

        # 2. Re-structure the data for easy lookup (same logic as seismo view)
        db_data = defaultdict(dict)
        for item in results:
            db_data[item['station']][item['date']] = item['average_percentage']

        # 3. Generate a complete date range
        date_range = [start_date + timedelta(days=x) for x in range((end_date - start_date).days + 1)]
        
        # 4. Create the final dataset, filling in missing dates with 0%
        final_data = defaultdict(list)
        for station in stations_to_include:
            for single_date in date_range:
                # Get the percentage if it exists, otherwise default to 0
                percentage = db_data[station].get(single_date, 0)
                final_data[station].append({
                    'date': single_date,
                    'percentage': percentage
                })
        
        stations_data = dict(final_data)

    context = {
        'stations_data_json': json.dumps(stations_data, cls=DjangoJSONEncoder) if stations_data else "{}",
        'stations_data': stations_data,
        'start_date': start_date_str,
        'end_date': end_date_str,
    }
    return render(request, 'repository/accelero_availability_query.html', context)



@login_required
def availability_matrix_view(request, sensor_type='seismo'):
    """
    View Generic untuk menampilkan Matriks Availability.
    Bisa menangani 'seismo' maupun 'accelero'.
    """
    # 1. Setup Konfigurasi Berdasarkan Tipe Sensor
    if sensor_type == 'accelero':
        ModelClass = AcceleroDataAvailability
        # Judul Halaman (H1)
        page_title = "Rekapitulasi Persentasi Hasil Monitoring Ketersediaan Data Akselerograf"
        # Nama Sensor untuk Judul Grafik
        sensor_name = "Akselerograf"
        
        # Daftar Stasiun Accelero
        station_list = [
            'ARKPI', 'ARPI', 'BMPI', 'BTSPI', 'DYPI', 'EDMPI', 'ELMPI', 'FKMPM', 
            'GENI', 'JBPI', 'JGPI', 'JMPI', 'KIMPI', 'LJPI', 'MIBPI', 'MMPI', 
            'MTJPI', 'MTMPI', 'OBMPI', 'SATPI', 'SKPM', 'SMPI', 'SOMPI', 'TMPI', 
            'TRPI', 'WAMI'
        ]
    else:
        # Default Seismo
        ModelClass = DataAvailability
        # Judul Halaman (H1)
        page_title = "Rekapitulasi Persentasi Hasil Monitoring Ketersediaan Data Seismik"
        # Nama Sensor untuk Judul Grafik
        sensor_name = "Seismik"
        
        # Daftar Stasiun Seismo
        station_list = [
            'ARPI', 'ARKPI', 'BTSPI', 'DYPI', 'EDMPI', 'ELMPI', 'FKMPM', 'GENI', 'JAY', 'KIMPI', 
            'LJPI', 'MIBPI', 'MMPI', 'MTJPI', 'MTMPI', 'OBMPI', 'SATPI', 'SJPM', 'SKPM','SMPI', 'SOMPI', 
            'SUSPI', 'TRPI', 'UWNPI', 'WAMI', 'WANPI', 'YBYPI'
        ]

    # 2. Setup Waktu
    today = datetime.now()
    try:
        selected_month = int(request.GET.get('month', today.month))
        selected_year = int(request.GET.get('year', today.year))
    except ValueError:
        selected_month = today.month
        selected_year = today.year

    _, num_days = calendar.monthrange(selected_year, selected_month)
    list_tanggal = list(range(1, num_days + 1))
    
    daftar_bulan_indo = [
        "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember"
    ]
    month_name = daftar_bulan_indo[selected_month]

    start_date = date(selected_year, selected_month, 1)
    end_date = date(selected_year, selected_month, num_days)

    # 3. Ambil Data (Generic Model)
    
    # A. Data Manual (Report)
    manual_data_query = ModelClass.objects.filter(
        station__in=station_list,
        date__range=[start_date, end_date],
        channel='REPORT'
    ).values('station', 'date', 'percentage')

    manual_map = {}
    for item in manual_data_query:
        key = (item['station'], item['date'].strftime('%Y-%m-%d'))
        manual_map[key] = item['percentage']

    # B. Data Raw (Mesin) - Rata-rata harian
    raw_data_query = ModelClass.objects.filter(
        station__in=station_list,
        date__range=[start_date, end_date]
    ).exclude(
        channel='REPORT'
    ).values('station', 'date').annotate(avg_pct=Avg('percentage'))

    raw_map = {}
    for item in raw_data_query:
        key = (item['station'], item['date'].strftime('%Y-%m-%d'))
        raw_map[key] = item['avg_pct']

    # For accelero: SLINKTOOL records override the averaged .D-channel records
    if sensor_type == 'accelero':
        slinktool_query = ModelClass.objects.filter(
            station__in=station_list,
            date__range=[start_date, end_date],
            channel='SLINKTOOL',
        ).values('station', 'date', 'percentage')
        for item in slinktool_query:
            key = (item['station'], item['date'].strftime('%Y-%m-%d'))
            raw_map[key] = item['percentage']

    # 4. Bangun Tabel
    tabel_data = []
    for stasiun in station_list:
        row = {'nama': stasiun, 'hari': [], 'avg_row': 0}
        total_val = 0
        
        for d in list_tanggal:
            curr_date = date(selected_year, selected_month, d)
            date_str = curr_date.strftime('%Y-%m-%d')
            key = (stasiun, date_str)
            
            val = 0.0
            if key in manual_map:
                val = manual_map[key]
            elif key in raw_map:
                val = raw_map[key]
            
            val = float(val)
            row['hari'].append({
                'day_num': d,
                'full_date': date_str,
                'val': val
            })
            total_val += val
            
        row['avg_row'] = round(total_val / num_days, 2)
        tabel_data.append(row)

    # Build OLA view: Hidup >75%, Gap 0%<x≤75%, Mati =0%
    def _ola_status(val):
        if val > 75:
            return 'hidup'
        if val > 0:
            return 'gap'
        return 'mati'

    on_off_data = []
    for row in tabel_data:
        hari = [
            {
                'day_num': d['day_num'],
                'full_date': d['full_date'],
                'status': _ola_status(d['val']),
            }
            for d in row['hari']
        ]
        on_off_row = {
            'nama': row['nama'],
            'hari': hari,
            'days_hidup': sum(1 for d in hari if d['status'] == 'hidup'),
        }
        on_off_data.append(on_off_row)

    context = {
        'tabel_data': tabel_data,
        'on_off_data': on_off_data,
        'list_tanggal': list_tanggal,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'month_name': month_name,
        'years_range': range(2020, 2030),
        'months_range': range(1, 13),
        'page_title': page_title,
        'sensor_name': sensor_name,
        'sensor_type': sensor_type,
    }

    return render(request, 'repository/data_availability_query.html', context)


@require_POST
@login_required
def update_availability_cell(request):
    """
    API AJAX Updated: Menangani simpan data untuk Seismo MAUPUN Accelero.
    """
    try:
        data = json.loads(request.body)
        station = data.get('station')
        date_str = data.get('date')
        val = float(data.get('value'))
        sensor_type = data.get('sensor_type', 'seismo') # Baca tipe sensor

        if val < 0 or val > 100:
            return JsonResponse({'status': 'error', 'message': 'Value must be 0-100'}, status=400)

        # Tentukan Model mana yang dipakai
        if sensor_type == 'accelero':
            ModelClass = AcceleroDataAvailability
        else:
            ModelClass = DataAvailability

        # Update or Create (Channel selalu REPORT)
        obj, created = ModelClass.objects.update_or_create(
            station=station,
            date=date_str,
            channel='REPORT', 
            defaults={'percentage': val}
        )

        return JsonResponse({
            'status': 'success', 
            'station': station, 
            'new_val': val
        })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
@login_required
def shakemap_report_query(request):
    """
    Laporan Shakemap Bulanan — primary model is FeltEarthquake.
    ShakemapEvent is looked up per-event to attach the MMI image and station readings.
    """
    today = datetime.now()
    try:
        selected_month = int(request.GET.get('month', today.month))
        selected_year = int(request.GET.get('year', today.year))
    except ValueError:
        selected_month = today.month
        selected_year = today.year

    daftar_bulan_indo = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
                         "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    month_name = daftar_bulan_indo[selected_month]

    _, num_days = calendar.monthrange(selected_year, selected_month)
    days_range_list = list(range(1, num_days + 1))

    # Primary queryset: FeltEarthquake
    _WIB = dt_timezone(timedelta(hours=7))
    events = list(
        FeltEarthquake.objects.filter(
            event_datetime__year=selected_year,
            event_datetime__month=selected_month,
        ).order_by('-event_datetime')
    )

    # Build wib_ts → ShakemapEvent map for this month so we can attach the MMI shakemap image
    shk_map = {
        shk.event_id: shk
        for shk in ShakemapEvent.objects.filter(
            event_time__year=selected_year,
            event_time__month=selected_month,
        )
    }

    for fe in events:
        wib_ts = fe.event_datetime.astimezone(_WIB).strftime("%Y%m%d%H%M%S")
        fe.wib_ts   = wib_ts
        fe.shk_event = shk_map.get(wib_ts)

    # --- Recap matrix (UTC slots) ---
    time_slots = [
        (0, 3,  "00 - 03"),
        (3, 6,  "03 - 06"),
        (6, 9,  "06 - 09"),
        (9, 12, "09 - 12"),
        (12, 15,"12 - 15"),
        (15, 18,"15 - 18"),
        (18, 21,"18 - 21"),
        (21, 24,"21 - 00"),
    ]

    recap_matrix = {i: {d: 0 for d in days_range_list} for i in range(len(time_slots))}
    row_totals   = {i: 0 for i in range(len(time_slots))}
    day_totals   = {d: 0 for d in days_range_list}
    grand_total  = 0

    for fe in events:
        dt = fe.event_datetime
        if timezone.is_aware(dt):
            dt = dt.astimezone(dt_timezone.utc)
        day  = dt.day
        hour = dt.hour
        for idx, (start, end, label) in enumerate(time_slots):
            if start <= hour < end:
                recap_matrix[idx][day] += 1
                row_totals[idx] += 1
                day_totals[day] += 1
                grand_total += 1
                break

    recap_data = [
        {
            'label': label,
            'days':  [recap_matrix[idx][d] if recap_matrix[idx][d] > 0 else "-" for d in days_range_list],
            'total': row_totals[idx],
        }
        for idx, (start, end, label) in enumerate(time_slots)
    ]

    context = {
        'events':         events,
        'selected_month': selected_month,
        'selected_year':  selected_year,
        'month_name':     month_name,
        'years_range':    range(2020, 2030),
        'months_range':   range(1, 13),
        'page_title':     f"Laporan Bulanan Shakemap - {month_name} {selected_year}",
        'recap_data':     recap_data,
        'day_totals':     [day_totals[d] for d in days_range_list],
        'grand_total':    grand_total,
        'days_range_list': days_range_list,
    }

    return render(request, 'repository/shakemap_report_query.html', context)

@login_required
def json_upload_create(request):
    """Handle JSON file upload"""
    if request.method == 'POST':
        json_file = request.FILES.get('json_file')
        
        if not json_file:
            return render(request, 'repository/json_upload.html', 
                         {'error': 'Silakan pilih file JSON'})
        
        try:
            # Read and validate JSON
            file_content = json_file.read().decode('utf-8')
            data = json.loads(file_content)
            
            # Extract metadata
            agency = data.get('agency', '')
            region = data.get('regional', '')
            bulan = data.get('bulan', '')
            data_count = len(data.get('data', []))
            
            # Replace existing upload for same user+bulan+agency, or create new
            existing = JSONDataUpload.objects.filter(
                user=request.user,
                bulan=bulan,
                agency=agency,
            ).first()

            if existing:
                if existing.json_file:
                    existing.json_file.delete(save=False)
                json_file.seek(0)
                existing.file_name = json_file.name
                existing.region = region
                existing.data_count = data_count
                existing.json_file = json_file
                existing.save()
                upload = existing
            else:
                upload = JSONDataUpload.objects.create(
                    user=request.user,
                    file_name=json_file.name,
                    agency=agency,
                    region=region,
                    bulan=bulan,
                    json_file=json_file,
                    data_count=data_count
                )

            return redirect('json_analysis', pk=upload.pk)
            
        except json.JSONDecodeError:
            return render(request, 'repository/json_upload.html',
                         {'error': 'File JSON tidak valid'})
        except Exception as e:
            return render(request, 'repository/json_upload.html',
                         {'error': f'Error: {str(e)}'})
    
    return render(request, 'repository/json_upload.html')
 
 
@login_required
def json_upload_list(request):
    """List all user's uploads"""
    uploads = JSONDataUpload.objects.filter(user=request.user).order_by('-uploaded_at')
    context = {'uploads': uploads}
    return render(request, 'repository/json_upload_list.html', context)
 
 
@login_required
def json_analysis(request, pk):
    """Analyze uploaded JSON data"""
    upload_obj = get_object_or_404(JSONDataUpload, pk=pk, user=request.user)
    
    # 1. Formatting Bulan Indonesia
    bulan_str = upload_obj.bulan.strip() if upload_obj.bulan else ""
    formatted_bulan = bulan_str.upper() # Fallback
    
    current_year = date.today().year
    current_month = date.today().month
    
    # Ekstrak YYYYMM atau YYYY-MM
    match = re.search(r'^(\d{4})[-_]?(\d{1,2})$', bulan_str)
    if match:
        current_year = int(match.group(1))
        current_month = int(match.group(2))
        daftar_bulan = ["", "JANUARI", "FEBRUARI", "MARET", "APRIL", "MEI", "JUNI", "JULI", "AGUSTUS", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DESEMBER"]
        if 1 <= current_month <= 12:
            formatted_bulan = f"{daftar_bulan[current_month]} {current_year}"

    # 2. Hitung jumlah hari dalam bulan untuk tabel dinamis
    _, num_days = calendar.monthrange(current_year, current_month)
    days_range = range(1, num_days + 1)

    try:
        # Read JSON file
        json_file = upload_obj.json_file.read().decode('utf-8')
        data = json.loads(json_file)
        events = data.get('data', [])

        # --- Save events to Gempa model ---
        agency = upload_obj.agency or 'UNKNOWN'
        saved_count = 0
        for ev in events:
            try:
                ev_time_str = ev.get('time', '')
                ev_dt = dateutil_parser.parse(ev_time_str)
                source_id = f"{ev_dt.strftime('%Y%m%d%H%M%S')}_{agency}"
                lat = float(ev.get('latitude', 0))
                lon = float(ev.get('longitude', 0))
                remark = calculate_remark(lat, lon)
                Gempa.objects.update_or_create(
                    source_id=source_id,
                    defaults={
                        'station_code': agency,
                        'origin_datetime': ev_dt,
                        'latitude': lat,
                        'longitude': lon,
                        'magnitudo': float(ev.get('magnitude', 0)),
                        'depth': int(ev.get('depth_km', 0)),
                        'remark': remark,
                    }
                )
                saved_count += 1
            except Exception:
                continue

        # 3. Ambil Data FeltEarthquake dari Database (Peta Dirasakan)
        _WIB = dt_timezone(timedelta(hours=7))
        felt_events_query = list(
            FeltEarthquake.objects.filter(
                event_datetime__year=current_year,
                event_datetime__month=current_month
            ).order_by('event_datetime')
        )

        # Attach ShakemapEvent (MMI image) to each FeltEarthquake
        shk_map = {
            shk.event_id: shk
            for shk in ShakemapEvent.objects.filter(
                event_time__year=current_year,
                event_time__month=current_month,
            )
        }
        for fe in felt_events_query:
            wib_ts = fe.event_datetime.astimezone(_WIB).strftime("%Y%m%d%H%M%S")
            fe.shk_event = shk_map.get(wib_ts)

        felt_map_data = []
        for fe in felt_events_query:
            felt_map_data.append({
                'lat': float(fe.latitude),
                'lon': float(fe.longitude),
                'mag': float(fe.magnitude),
                'place': fe.wilayah,
                'time': fe.event_datetime.strftime('%Y-%m-%d %H:%M')
            })
            
        # 4. Daftar Perangkat SeisComP untuk Status Alat
        seiscomp_components = [
            "KOMPUTER MASTER PRO",
            "MAP VIEW SEISCOMP4",
            "TRACE VIEW SINYAL",
            "ORIGIN LOCATION VIEW",
            "EVENT SUMMARY VIEW",
            "KOMPUTER DATA EXCHANGE"
        ]
            
        # Calculate statistics
        magnitudes = [e.get('magnitude', 0) for e in events]
        depths = [e.get('depth_km', 0) for e in events]
        
        stats = {
            'total': len(events),
            'avg_magnitude': round(sum(magnitudes) / len(magnitudes), 2) if magnitudes else 0,
            'min_magnitude': round(min(magnitudes), 2) if magnitudes else 0,
            'max_magnitude': round(max(magnitudes), 2) if magnitudes else 0,
            'avg_depth': round(sum(depths) / len(depths), 2) if depths else 0,
            'min_depth': round(min(depths), 2) if depths else 0,
            'max_depth': round(max(depths), 2) if depths else 0,
        }
        
        mag_categories = {
            'M<3': len([e for e in events if e.get('magnitude', 0) < 3]),
            'M 3-5': len([e for e in events if 3 <= e.get('magnitude', 0) < 5]),
            'M≥5': len([e for e in events if e.get('magnitude', 0) >= 5]),
        }
        
        depth_categories = {
            'D<60': len([e for e in events if e.get('depth_km', 0) < 60]),
            'D 60-300': len([e for e in events if 60 <= e.get('depth_km', 0) < 300]),
            'D>300': len([e for e in events if e.get('depth_km', 0) >= 300]),
        }
        
        # Build map_data from saved Gempa records (has remark/lokasi)
        gempa_qs = Gempa.objects.filter(
            station_code=agency,
            origin_datetime__year=current_year,
            origin_datetime__month=current_month,
        ).order_by('origin_datetime')

        map_data = []
        for g in gempa_qs:
            map_data.append({
                'latitude': float(g.latitude),
                'longitude': float(g.longitude),
                'magnitude': float(g.magnitudo),
                'depth': float(g.depth),
                'time': g.origin_datetime.strftime('%Y-%m-%dT%H:%M:%S'),
                'event_id': g.source_id or '',
                'location': g.remark,
            })

        if not map_data:
            for event in events:
                map_data.append({
                    'latitude': event.get('latitude', 0),
                    'longitude': event.get('longitude', 0),
                    'magnitude': event.get('magnitude', 0),
                    'depth': event.get('depth_km', 0),
                    'time': event.get('time', ''),
                    'event_id': event.get('event_id', ''),
                    'location': '',
                })

        if map_data:
            avg_lat = sum([e['latitude'] for e in map_data]) / len(map_data)
            avg_lon = sum([e['longitude'] for e in map_data]) / len(map_data)
        else:
            avg_lat, avg_lon = 0, 0
        
        # QC Reviewer data untuk bulan yang sama
        qc_map_data = _qc_map_entries_by_month(current_year, current_month)
        qc_stats = {
            'total':   len(qc_map_data),
            'max_mag': round(max((e['magnitude'] for e in qc_map_data), default=0), 1),
            'mag_lt3': len([e for e in qc_map_data if e['magnitude'] < 3]),
            'mag_35':  len([e for e in qc_map_data if 3 <= e['magnitude'] < 5]),
            'mag_gte5':len([e for e in qc_map_data if e['magnitude'] >= 5]),
            'dep_lt60':   len([e for e in qc_map_data if e['depth'] < 60]),
            'dep_mid':    len([e for e in qc_map_data if 60 <= e['depth'] < 300]),
            'dep_deep':   len([e for e in qc_map_data if e['depth'] >= 300]),
        }

        nama_upt = "STASIUN GEOFISIKA KELAS I JAYAPURA"
        context = {
            'upload_obj': upload_obj,
            'upt': nama_upt,
            'formatted_bulan': formatted_bulan,
            'days_range': days_range,
            'num_days': num_days,
            'felt_map_data': json.dumps(felt_map_data),
            'felt_events': felt_events_query,
            'seiscomp_components': seiscomp_components,
            'stats': stats,
            'mag_categories': mag_categories,
            'mag_count_low': mag_categories.get('M<3', 0),
            'mag_count_mid': mag_categories.get('M 3-5', 0),
            'mag_count_high': mag_categories.get('M≥5', 0),
            'depth_categories': depth_categories,
            'depth_count_shallow': depth_categories.get('D<60', 0),
            'depth_count_mid': depth_categories.get('D 60-300', 0),
            'depth_count_deep': depth_categories.get('D>300', 0),
            'map_data': json.dumps(map_data),
            'qc_map_data': json.dumps(qc_map_data, cls=DjangoJSONEncoder),
            'qc_stats': qc_stats,
            'avg_lat': avg_lat,
            'avg_lon': avg_lon,
            'events': events[:50],
            'total_events': len(events),
        }
        
        return render(request, 'repository/json_analysis.html', context)
        
    except Exception as e:
        context = {'error': f'Error processing file: {str(e)}'}
        return render(request, 'repository/json_analysis.html', context)
 
 
@login_required
def json_delete(request, pk):
    """Delete uploaded JSON file"""
    upload_obj = get_object_or_404(JSONDataUpload, pk=pk, user=request.user)
    
    if request.method == 'POST':
        # Delete file from storage
        if upload_obj.json_file:
            upload_obj.json_file.delete()
        # Delete database record
        upload_obj.delete()
        return redirect('json_upload_list')
    
    context = {'upload_obj': upload_obj}
    return render(request, 'repository/json_delete_confirm.html', context)

# ── Gempa Merusak CRUD ────────────────────────────────────────────────────────

@login_required
def gempa_merusak_list(request):
    qs = GempaMemusak.objects.prefetch_related('media').all()
    q = request.GET.get('q', '').strip()
    provinsi = request.GET.get('provinsi', '').strip()
    tsunami = request.GET.get('tsunami', '').strip()
    if q:
        qs = qs.filter(Q(tanggal_text__icontains=q) | Q(wilayah__icontains=q) | Q(korban_kerusakan__icontains=q))
    if provinsi:
        qs = qs.filter(provinsi=provinsi)
    if tsunami == '1':
        qs = qs.filter(tsunami=True)
    elif tsunami == '0':
        qs = qs.filter(tsunami=False)

    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="gempa_merusak.csv"'
        response.write('﻿')  # BOM for Excel UTF-8
        writer = csv.writer(response)
        writer.writerow(['No', 'Tanggal', 'Wilayah', 'Provinsi', 'Origin Time',
                         'Latitude', 'Longitude', 'Kedalaman (km)', 'Magnitudo',
                         'Lokasi', 'Tsunami', 'Wilayah Merasakan', 'Korban/Kerusakan', 'Sumber'])
        for obj in qs:
            tsunami_val = 'Ya' if obj.tsunami is True else ('Tidak' if obj.tsunami is False else '')
            writer.writerow([
                obj.no, obj.tanggal_text, obj.wilayah, obj.provinsi,
                obj.origin_time or '', obj.latitude or '', obj.longitude or '',
                obj.depth_km or '', obj.magnitude or '', obj.lokasi,
                tsunami_val, obj.wilayah_merasakan, obj.korban_kerusakan, obj.sumber,
            ])
        return response

    return render(request, 'repository/gempa_merusak_list.html', {
        'object_list': qs,
        'province_choices': GempaMemusak.PROVINCE_CHOICES,
        'filter_q': q,
        'filter_provinsi': provinsi,
        'filter_tsunami': tsunami,
    })


@login_required
def gempa_merusak_detail(request, pk):
    obj = get_object_or_404(GempaMemusak, pk=pk)
    return render(request, 'repository/gempa_merusak_detail.html', {'object': obj})


@login_required
def gempa_merusak_create(request):
    if request.method == 'POST':
        obj = _save_gempa_merusak(request, GempaMemusak())
        _handle_media_uploads(request, obj)
        return redirect('gempa_merusak_list')
    return render(request, 'repository/gempa_merusak_form.html', {
        'province_choices': GempaMemusak.PROVINCE_CHOICES,
        'lokasi_choices': GempaMemusak.LOKASI_CHOICES,
        'title': 'Tambah Gempa Merusak',
    })


@login_required
def gempa_merusak_update(request, pk):
    obj = get_object_or_404(GempaMemusak, pk=pk)
    if request.method == 'POST':
        _save_gempa_merusak(request, obj)
        _handle_media_uploads(request, obj)
        # handle media deletions
        delete_ids = request.POST.getlist('delete_media')
        if delete_ids:
            for m in GempaMemusakMedia.objects.filter(pk__in=delete_ids, event=obj):
                m.file.delete(save=False)
                m.delete()
        return redirect('gempa_merusak_detail', pk=obj.pk)
    return render(request, 'repository/gempa_merusak_form.html', {
        'object': obj,
        'province_choices': GempaMemusak.PROVINCE_CHOICES,
        'lokasi_choices': GempaMemusak.LOKASI_CHOICES,
        'title': 'Edit Gempa Merusak',
    })


@login_required
def gempa_merusak_delete(request, pk):
    obj = get_object_or_404(GempaMemusak, pk=pk)
    if request.method == 'POST':
        for m in obj.media.all():
            m.file.delete(save=False)
        obj.delete()
        return redirect('gempa_merusak_list')
    return render(request, 'repository/gempa_merusak_confirm_delete.html', {'object': obj})


def _save_gempa_merusak(request, obj):
    p = request.POST
    obj.no               = int(p.get('no', 0))
    obj.tanggal_text     = p.get('tanggal_text', '').strip()
    obj.tanggal          = p.get('tanggal') or None
    obj.wilayah          = p.get('wilayah', '').strip()
    obj.provinsi         = p.get('provinsi', '').strip()
    obj.origin_time      = p.get('origin_time') or None
    obj.latitude         = float(p['latitude']) if p.get('latitude') else None
    obj.longitude        = float(p['longitude']) if p.get('longitude') else None
    obj.depth_km         = float(p['depth_km']) if p.get('depth_km') else None
    obj.magnitude        = float(p['magnitude']) if p.get('magnitude') else None
    obj.lokasi           = p.get('lokasi', '').strip()
    tsunami_val          = p.get('tsunami', '')
    obj.tsunami          = True if tsunami_val == '1' else (False if tsunami_val == '0' else None)
    obj.wilayah_merasakan = p.get('wilayah_merasakan', '').strip()
    obj.korban_kerusakan = p.get('korban_kerusakan', '').strip()
    obj.sumber           = p.get('sumber', '').strip()
    obj.save()
    return obj


def _handle_media_uploads(request, obj):
    files = request.FILES.getlist('media_files')
    media_type = request.POST.get('media_type_new', GempaMemusakMedia.TYPE_IMAGE)
    caption    = request.POST.get('caption_new', '')
    for f in files:
        GempaMemusakMedia.objects.create(event=obj, file=f, media_type=media_type, caption=caption)


# ── Event Browser ─────────────────────────────────────────────────────────────
def _qc_entry(e):
    """Build a map-data dict from a QCEvent using its latest run snapshot."""
    run = e.latest_run
    if not run:
        return None
    ot = run.snap_origin_time or e.origin_time
    return {
        'latitude':   float(run.snap_latitude  if run.snap_latitude  is not None else (e.latitude  or 0)),
        'longitude':  float(run.snap_longitude if run.snap_longitude is not None else (e.longitude or 0)),
        'magnitude':  float(run.snap_magnitude if run.snap_magnitude is not None else (e.magnitude or 0)),
        'depth':      float(run.snap_depth_km  if run.snap_depth_km  is not None else (e.depth_km  or 0)),
        'time':       ot.strftime('%Y-%m-%d %H:%M:%S UTC') if ot else '–',
        'event_id':   e.public_id,
        'location':   run.snap_region or e.region or '',
        'source':     'qc',
        'run_number': run.run_number,
        'eval_status': run.evaluation_status or '',
    }


def _qc_map_entries_by_date(start, end):
    from qc_review.models import Event as QCEvent
    qs = QCEvent.objects.filter(
        origin_time__date__gte=start,
        origin_time__date__lte=end,
    ).prefetch_related('runs')
    return [e for e in (_qc_entry(ev) for ev in qs) if e is not None]


def _qc_map_entries_by_month(year, month):
    from qc_review.models import Event as QCEvent
    qs = QCEvent.objects.filter(
        origin_time__year=year,
        origin_time__month=month,
    ).prefetch_related('runs')
    return [e for e in (_qc_entry(ev) for ev in qs) if e is not None]


@login_required
def event_browser(request):
    from .models import EventBrowser
    today = date.today()
    default_start = today - timedelta(days=6)

    start_str = request.GET.get('start', default_start.isoformat())
    end_str   = request.GET.get('end',   today.isoformat())
    try:
        start = date.fromisoformat(start_str)
        end   = date.fromisoformat(end_str)
    except ValueError:
        start, end = default_start, today

    qs = EventBrowser.objects.filter(
        origin_time__date__gte=start,
        origin_time__date__lte=end,
    ).order_by('-origin_time')

    map_data = []
    lats, lons = [], []
    for ev in qs.values('event_id', 'latitude', 'longitude', 'magnitude', 'depth_km', 'origin_time', 'location', 'nearest_city', 'distance_km'):
        dist = ev['distance_km']
        map_data.append({
            'event_id':     ev['event_id'],
            'latitude':     ev['latitude'],
            'longitude':    ev['longitude'],
            'magnitude':    ev['magnitude'],
            'depth':        ev['depth_km'],
            'time':         ev['origin_time'].strftime('%Y-%m-%d %H:%M:%S UTC'),
            'location':     ev['location'],
            'nearest_city': ev['nearest_city'],
            'distance_km':  round(dist, 1) if dist is not None and dist != float('inf') else None,
        })
        lats.append(ev['latitude'])
        lons.append(ev['longitude'])

    avg_lat = round(sum(lats) / len(lats), 4) if lats else -2.5
    avg_lon = round(sum(lons) / len(lons), 4) if lons else 137.5
    formatted_period = f"{start.strftime('%d %B %Y')} s/d {end.strftime('%d %B %Y')}"

    # Peta Dirasakan — FeltEarthquake within the selected date range
    _WIB = dt_timezone(timedelta(hours=7))
    felt_events_query = list(
        FeltEarthquake.objects.filter(
            event_datetime__date__gte=start,
            event_datetime__date__lte=end,
        ).order_by('event_datetime')
    )
    shk_map = {
        shk.event_id: shk
        for shk in ShakemapEvent.objects.filter(
            event_time__date__gte=start,
            event_time__date__lte=end,
        )
    }
    for fe in felt_events_query:
        wib_ts = fe.event_datetime.astimezone(_WIB).strftime('%Y%m%d%H%M%S')
        fe.shk_event = shk_map.get(wib_ts)

    felt_map_data = [
        {
            'lat':   float(fe.latitude),
            'lon':   float(fe.longitude),
            'mag':   float(fe.magnitude),
            'place': fe.wilayah,
            'time':  fe.event_datetime.strftime('%Y-%m-%d %H:%M'),
        }
        for fe in felt_events_query
    ]

    # QC Reviewer data untuk rentang tanggal yang sama
    qc_map_data = _qc_map_entries_by_date(start, end)

    context = {
        'map_data':        json.dumps(map_data, cls=DjangoJSONEncoder),
        'felt_map_data':   json.dumps(felt_map_data),
        'qc_map_data':     json.dumps(qc_map_data, cls=DjangoJSONEncoder),
        'felt_events':     felt_events_query,
        'avg_lat':         avg_lat,
        'avg_lon':         avg_lon,
        'formatted_bulan': formatted_period,
        'start':           start.isoformat(),
        'end':             end.isoformat(),
        'count':           len(map_data),
        'total_db':        EventBrowser.objects.count(),
        'stats': {
            'total':   len(map_data),
            'max_mag': max((e['magnitude'] for e in map_data), default=0),
        },
        'qc_stats': {
            'total':   len(qc_map_data),
            'max_mag': round(max((e['magnitude'] for e in qc_map_data), default=0), 1),
        },
    }
    return render(request, 'repository/event_browser.html', context)


# ---------------------------------------------------------------------------
# QuakeLink push API — accepts batched events from remote scrapers
# POST /api/events/push/   Authorization: Bearer <QUAKELINK_PUSH_TOKEN>
# ---------------------------------------------------------------------------
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings as dj_settings
import math as _math

_DIRECTIONS_PUSH = ['Utara', 'Timur Laut', 'Timur', 'Tenggara', 'Selatan', 'Barat Daya', 'Barat', 'Barat Laut']

_PROV_SUFFIXES_PUSH = {
    'PAPUA', 'PAPUABRT', 'PAPUABRTDY', 'PAPUASEL', 'PAPUATENGAH', 'PAPUAPEGNGN',
    'PAPUANUGINI', 'MALUKU', 'MALUKUUTARA', 'SULUT', 'SULTRA', 'SULTENG', 'SULSEL',
}

_SUBDISTRICT_PREFIXES_PUSH = {'LEREH', 'GENYEM', 'KEBAR', 'SENGGI'}
_ADMIN_LABELS_PUSH = {'KAB': 'Kab.', 'KOTA': 'Kota', 'PEG': 'Peg.'}

def _clean_city_push(name):
    parts = [p.strip() for p in name.strip().replace(' - ', '-').split('-')]
    while len(parts) > 1:
        tail = parts[-1].upper().replace(' ', '')
        combined = (parts[-2].upper().replace(' ', '') + parts[-1].upper().replace(' ', ''))
        if combined in _PROV_SUFFIXES_PUSH:
            parts = parts[:-2]
        elif tail in _PROV_SUFFIXES_PUSH:
            parts.pop()
        else:
            break
    if len(parts) == 1:
        return parts[0].title()
    first_up = parts[0].upper()
    if first_up in _ADMIN_LABELS_PUSH:
        return _ADMIN_LABELS_PUSH[first_up] + ' ' + ' '.join(p.title() for p in parts[1:])
    if first_up in _SUBDISTRICT_PREFIXES_PUSH:
        return ' '.join(p.title() for p in parts[1:])
    return ' '.join(p.title() for p in parts)

def _hav(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = _math.radians(lat2 - lat1)
    dlon = _math.radians(lon2 - lon1)
    a = _math.sin(dlat/2)**2 + _math.cos(_math.radians(lat1)) * _math.cos(_math.radians(lat2)) * _math.sin(dlon/2)**2
    return R * 2 * _math.asin(_math.sqrt(a))

def _brng(lat1, lon1, lat2, lon2):
    dlon = _math.radians(lon2 - lon1)
    lat1r, lat2r = _math.radians(lat1), _math.radians(lat2)
    x = _math.sin(dlon) * _math.cos(lat2r)
    y = _math.cos(lat1r) * _math.sin(lat2r) - _math.sin(lat1r) * _math.cos(lat2r) * _math.cos(dlon)
    return (_math.degrees(_math.atan2(x, y)) + 360) % 360

def _nearest(lat, lon, cities):
    if not cities:
        return '', None
    best, bd = None, float('inf')
    for c in cities:
        d = _hav(lat, lon, c.latitude, c.longitude)
        if d < bd:
            bd, best = d, c
    direction = _DIRECTIONS_PUSH[round(_brng(best.latitude, best.longitude, lat, lon) / 45) % 8]
    return f"{round(bd)} km {direction} {_clean_city_push(best.name)}", round(bd, 1)


@csrf_exempt
def push_events_api(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    token = request.headers.get('Authorization', '').removeprefix('Bearer ').strip()
    expected = getattr(dj_settings, 'QUAKELINK_PUSH_TOKEN', '')
    if not expected or token != expected:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        events = json.loads(request.body)
        if not isinstance(events, list):
            raise ValueError
    except (ValueError, Exception):
        return JsonResponse({'error': 'Expected JSON array'}, status=400)

    from .models import EventBrowser, ReferenceLocation
    cities = list(ReferenceLocation.objects.all())
    new_count = updated_count = 0

    for ev in events:
        try:
            lat  = float(ev['latitude'])
            lon  = float(ev['longitude'])
            city_label, dist = _nearest(lat, lon, cities)
            obj, created = EventBrowser.objects.update_or_create(
                event_id=ev['event_id'],
                defaults={
                    'origin_time':  datetime.fromisoformat(ev['origin_time']),
                    'magnitude':    float(ev['magnitude']),
                    'latitude':     lat,
                    'longitude':    lon,
                    'depth_km':     float(ev['depth_km']),
                    'location':     ev.get('location', ''),
                    'author':       ev.get('author', ''),
                    'nearest_city': city_label,
                    'distance_km':  dist,
                },
            )
            if created:
                new_count += 1
            else:
                updated_count += 1
        except Exception:
            continue

    return JsonResponse({'new': new_count, 'updated': updated_count})
