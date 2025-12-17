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
from .models import AcceleroDataAvailability, StationReading
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
    model = ShakemapEvent
    context_object_name = 'shakemap_list'
    template_name = 'repository/shakemapevent_list.html'
    ordering = ['-event_time']
    paginate_by = 10
    
    def get_context_data(self, **kwargs):
        """
        Overrides the default context to add the total record count.
        """
        # Call the base implementation first to get the existing context
        context = super().get_context_data(**kwargs)
    
        # Add the total number of records to the context
        # context['paginator'].count is efficient as it's already calculated for pagination
        context['record_count'] = context['paginator'].count
        
        return context


# Renamed class and updated model and template
class ShakemapDetailView(generic.DetailView):
    model = ShakemapEvent
    template_name = 'repository/shakemapevent_detail.html'

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
    """
    Handles the deletion of a single ShakemapEvent.
    It will render a confirmation page before deleting.
    """
    model = ShakemapEvent
    template_name = 'repository/shakemapevent_confirm_delete.html'
    
    # After a successful deletion, redirect the user to the shakemap list page
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
            'LJPI', 'MIBPI', 'MMPI', 'MTJPI', 'MTMPI', 'OBMPI', 'SATPI', 'SJPM', 'SKPM', 'SOMPI', 
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

        context = {
                'tabel_data': tabel_data,
                'list_tanggal': list_tanggal,
                'selected_month': selected_month,
                'selected_year': selected_year,
                'month_name': month_name,
                'years_range': range(2020, 2030),
                'months_range': range(1, 13),
                
                # --- VARIABEL BARU UNTUK JUDUL DINAMIS ---
                'page_title': page_title,    # Untuk H1
                'sensor_name': sensor_name,  # Untuk H3 (Grafik)
                'sensor_type': sensor_type,  # Untuk AJAX
            }

    # Kita gunakan template yang sama untuk keduanya
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
    View khusus untuk Laporan Shakemap Bulanan.
    Menampilkan Event dan Station Reading dalam format list/tabel untuk dicetak.
    Ditambah dengan Rekapitulasi Matriks per Jam (3-jam) vs Tanggal.
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

    # Hitung jumlah hari dalam bulan terpilih
    _, num_days = calendar.monthrange(selected_year, selected_month)
    days_range_list = list(range(1, num_days + 1))

    # Query Events
    events = ShakemapEvent.objects.filter(
        event_time__year=selected_year,
        event_time__month=selected_month
    ).order_by('-event_time').prefetch_related('stations')

    # --- LOGIKA REKAPITULASI (MATRIX) ---
    # Slot waktu UTC (Start, End, Label)
    time_slots = [
        (0, 3, "00 - 03"),
        (3, 6, "03 - 06"),
        (6, 9, "06 - 09"),
        (9, 12, "09 - 12"),
        (12, 15, "12 - 15"),
        (15, 18, "15 - 18"),
        (18, 21, "18 - 21"),
        (21, 24, "21 - 00"),
    ]

    # Inisialisasi Matriks Kosong: matrix[slot_index][day] = count
    recap_matrix = {i: {d: 0 for d in days_range_list} for i in range(len(time_slots))}
    row_totals = {i: 0 for i in range(len(time_slots))}
    day_totals = {d: 0 for d in days_range_list}
    grand_total = 0

    for event in events:
        # Pastikan waktu dalam UTC agar sesuai dengan label tabel
        dt = event.event_time
        if timezone.is_aware(dt):
            dt = dt.astimezone(dt_timezone.utc)
        
        day = dt.day
        hour = dt.hour
        
        # Tentukan masuk slot mana
        slot_idx = -1
        for idx, (start, end, label) in enumerate(time_slots):
            if start <= hour < end:
                slot_idx = idx
                break
        
        # Update counter jika slot ditemukan
        if slot_idx != -1:
            recap_matrix[slot_idx][day] += 1
            row_totals[slot_idx] += 1
            day_totals[day] += 1
            grand_total += 1

    # Siapkan data untuk dilempar ke template
    recap_data = []
    for idx, (start, end, label) in enumerate(time_slots):
        row_days = []
        for d in days_range_list:
            count = recap_matrix[idx][d]
            # Gunakan "-" jika 0 agar tabel lebih bersih, atau angka 0 sesuai selera
            display_val = count if count > 0 else "-" 
            row_days.append(display_val)
        
        recap_data.append({
            'label': label,
            'days': row_days,
            'total': row_totals[idx]
        })

    context = {
        'events': events,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'month_name': month_name,
        'years_range': range(2020, 2030),
        'months_range': range(1, 13),
        'page_title': f"Laporan Bulanan Shakemap - {month_name} {selected_year}",
        
        # Context Baru untuk Tabel Rekap
        'recap_data': recap_data,
        'day_totals': [day_totals[d] for d in days_range_list],
        'grand_total': grand_total,
        'days_range_list': days_range_list,
    }

    return render(request, 'repository/shakemap_report_query.html', context)