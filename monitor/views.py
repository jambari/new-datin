from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, JsonResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import EarthquakeEvent
from .serializers import EarthquakeEventSerializer
import csv
from datetime import datetime, timedelta
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import requests
from django.contrib.gis.geos import GEOSGeometry, Point
import json
import os
from django.conf import settings
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from repository.models import ShakemapEvent

# --- API View (Penerima Data dari Windows) ---
@api_view(['POST'])
def receive_event_data(request):
    data = request.data
    try:
        if isinstance(data, list):
            count = 0
            for item in data:
                process_single_event(item)
                count += 1
            return Response({"status": "success", "message": f"{count} events processed"})
        else:
            process_single_event(data)
            return Response({"status": "success", "message": "Event processed"})
    except Exception as e:
        return Response({"status": "error", "message": str(e)}, status=400)

def process_single_event(data):
    event_id = data.get('event_id')
    serializer = EarthquakeEventSerializer(data=data)
    
    if serializer.is_valid():
        validated_data = serializer.validated_data
        
        # --- LOGIKA BARU: AUTO-FILL LOCATION (GEOMETRY) ---
        lat = validated_data.get('latitude')
        lon = validated_data.get('longitude')
        
        # Pastikan lat/lon ada, lalu buat Point GeoDjango
        # PENTING: Format Point adalah (Longitude, Latitude) -> (X, Y)
        if lat is not None and lon is not None:
            validated_data['location'] = Point(float(lon), float(lat))
            
        # Hapus event_id dari validated_data karena sudah dipakai di lookup
        validated_data.pop('event_id', None)
        
        # Simpan ke Database (Update jika ada, Create jika baru)
        EarthquakeEvent.objects.update_or_create(
            event_id=event_id, 
            defaults=validated_data
        )

# --- Public View (HTML Table) ---
def public_event_list(request):
    events = EarthquakeEvent.objects.all()

    # --- FILTER GEOMETRY (PGR5) ---
    use_pgr5 = request.GET.get('use_pgr5')
    if use_pgr5 == 'true':
        # Load file GeoJSON
        geojson_path = os.path.join(settings.STATIC_ROOT, 'pgr5.geojson') #
        
        with open(geojson_path) as f:
            geojson_data = json.load(f)
            
        # Ambil geometry dari Feature pertama
        # (Asumsi struktur GeoJSON standar FeatureCollection)
        geometry_dict = geojson_data['features'][0]['geometry'] 
        pgr5_polygon = GEOSGeometry(json.dumps(geometry_dict))
        
        # MAGIC FILTER: Cari event yang TITIKNYA benar-benar DI DALAM Polygon
        events = events.filter(location__within=pgr5_polygon)

    # --- FILTERING ---
    # 1. Agency Filter
    agency = request.GET.get('agency')
    if agency: events = events.filter(agency__iexact=agency)

    # 2. Status Filter
    status = request.GET.get('status')
    if status: events = events.filter(status__iexact=status)

    # 3. Magnitude Filter
    min_mag = request.GET.get('min_mag')
    max_mag = request.GET.get('max_mag')
    if min_mag: events = events.filter(magnitude__gte=min_mag)
    if max_mag: events = events.filter(magnitude__lte=max_mag)

    # 4. Depth Filter
    min_depth = request.GET.get('min_depth')
    max_depth = request.GET.get('max_depth')
    if min_depth: events = events.filter(depth__gte=min_depth)
    if max_depth: events = events.filter(depth__lte=max_depth)

    # 5. Date Filter
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    if start_date: events = events.filter(origin_time__date__gte=start_date)
    if end_date: events = events.filter(origin_time__date__lte=end_date)

    # 6. Coordinate Filter
    min_lat = request.GET.get('min_lat')
    max_lat = request.GET.get('max_lat')
    min_lon = request.GET.get('min_lon')
    max_lon = request.GET.get('max_lon')
    
    if min_lat: events = events.filter(latitude__gte=min_lat)
    if max_lat: events = events.filter(latitude__lte=max_lat)
    if min_lon: events = events.filter(longitude__gte=min_lon)
    if max_lon: events = events.filter(longitude__lte=max_lon)

    # --- Fetch Dropdown Options (NEW) ---
    # Mengambil list unik Agency yang ada di database, urut abjad, exclude yang kosong
    agency_options = EarthquakeEvent.objects.exclude(agency__isnull=True)\
                                            .exclude(agency__exact='')\
                                            .values_list('agency', flat=True)\
                                            .distinct().order_by('agency')

    # Mengambil list unik Status
    status_options = EarthquakeEvent.objects.exclude(status__isnull=True)\
                                            .exclude(status__exact='')\
                                            .values_list('status', flat=True)\
                                            .distinct().order_by('status')

    events = events.order_by('-origin_time')

    # --- EXPORT TO EXCEL ---
    if request.GET.get('export') == 'true':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="gempa_export_{datetime.now().strftime("%Y%m%d_%H%M")}.csv"'
        writer = csv.writer(response)
        writer.writerow(['Event ID', 'Waktu (UTC)', 'Magnitudo', 'Latitude', 'Longitude', 'Kedalaman (km)', 'Wilayah', 'Agency', 'Status', 'Fase'])
        for event in events:
            writer.writerow([
                event.event_id, event.origin_time.strftime("%Y-%m-%d %H:%M:%S"),
                event.magnitude, event.latitude, event.longitude, event.depth,
                event.region, event.agency, event.status, event.phases
            ])
        return response

    # --- PAGINATION ---
    per_page = request.GET.get('per_page', '20')
    if per_page == 'all':
        paginator = Paginator(events, events.count() if events.count() > 0 else 1)
    else:
        try: paginator = Paginator(events, int(per_page))
        except ValueError: paginator = Paginator(events, 20)

    page_number = request.GET.get('page')
    try: events_page = paginator.page(page_number)
    except PageNotAnInteger: events_page = paginator.page(1)
    except EmptyPage: events_page = paginator.page(paginator.num_pages)

    context = {
        'events': events_page,
        'filters': request.GET,
        'count': events.count(),
        'per_page': per_page,
        # Kirim opsi dropdown ke template
        'agency_options': agency_options,
        'status_options': status_options,
    }
    return render(request, 'monitor/public_event_list.html', context)

# --- NEW: Export All JSON ---
def export_all_json(request):
    events = EarthquakeEvent.objects.all()

    agency = request.GET.get('agency')
    if agency: events = events.filter(agency__iexact=agency)
    status = request.GET.get('status')
    if status: events = events.filter(status__iexact=status)
    min_mag = request.GET.get('min_mag')
    max_mag = request.GET.get('max_mag')
    if min_mag: events = events.filter(magnitude__gte=min_mag)
    if max_mag: events = events.filter(magnitude__lte=max_mag)
    
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    if start_date: events = events.filter(origin_time__date__gte=start_date)
    if end_date: events = events.filter(origin_time__date__lte=end_date)

    events = events.order_by('-origin_time')

    data = list(events.values(
        'event_id', 'origin_time', 'magnitude', 'latitude', 'longitude', 
        'depth', 'region', 'agency', 'status', 'phases'
    ))

    return JsonResponse({'count': len(data), 'data': data}, safe=False)

def webgis_event_detail(request, event_id):
    """
    Menampilkan halaman WebGIS khusus untuk satu event gempa.
    """
    event = get_object_or_404(EarthquakeEvent, event_id=event_id)
    
    context = {
        'event': event,
    }
    return render(request, 'monitor/webgis_detail.html', context)

def seismicity_analysis(request):
    events = EarthquakeEvent.objects.all()
    
# --- LOGIKA FILTER ---
    agency = request.GET.get('agency')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if agency == 'PGR_V_ALL':
        # List akurat untuk PGR V (Total ~208)
        events = events.filter(agency__in=['BMKG-JAY', 'BMKG-NBPI', 'PGR5', 'BMKG-SWI'])
    elif agency == 'PGR_1_ALL':
        # Filter baru untuk PGR I
        events = events.filter(agency__in=['BMKG-BSI', 'BMKG-DSI', 'BMKG-GSI', 'PGR1'])
    elif agency:
        events = events.filter(agency__iexact=agency)

    if start_date: events = events.filter(origin_time__date__gte=start_date)
    if end_date: events = events.filter(origin_time__date__lte=end_date)

# --- TAMBAHAN: LOGIKA EXPORT CSV ---
    if request.GET.get('export') == 'true':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="analisis_gempa_{datetime.now().strftime("%Y%m%d")}.csv"'
        writer = csv.writer(response)
        writer.writerow(['Event ID', 'Waktu (UTC)', 'Magnitudo', 'Lat', 'Lon', 'Kedalaman', 'Wilayah', 'Agency'])
        for e in events.order_by('-origin_time'):
            writer.writerow([e.event_id, e.origin_time, e.magnitude, e.latitude, e.longitude, e.depth, e.region, e.agency])
        return response

    # --- AMBIL DATA SHAKEMAP (REPOSITORY) ---
    felt_events = ShakemapEvent.objects.all()
    if start_date: felt_events = felt_events.filter(event_time__date__gte=start_date)
    if end_date: felt_events = felt_events.filter(event_time__date__lte=end_date)
    felt_events = felt_events.order_by('-event_time')

    # --- STATISTIK ---
    stats = {
        'total': events.count(),
        'felt': felt_events.count(),
        'm_lt_3': events.filter(magnitude__lt=3.0).count(),
        'm_3_5': events.filter(magnitude__gte=3.0, magnitude__lt=5.0).count(),
        'm_gt_5': events.filter(magnitude__gte=5.0).count(),
        'd_lt_60': events.filter(depth__lt=60).count(),
        'd_60_300': events.filter(depth__gte=60, depth__lt=300).count(),
        'd_gt_300': events.filter(depth__gte=300).count(),
    }

    daily_stats = events.annotate(date=TruncDate('origin_time')).values('date').annotate(
        total=Count('event_id'),
        m_lt_3=Count('event_id', filter=Q(magnitude__lt=3.0)),
        m_3_5=Count('event_id', filter=Q(magnitude__gte=3.0, magnitude__lt=5.0)),
        m_gt_5=Count('event_id', filter=Q(magnitude__gte=5.0)),
        d_lt_60=Count('event_id', filter=Q(depth__lt=60)),
        d_60_300=Count('event_id', filter=Q(depth__gte=60, depth__lt=300)),
        d_gt_300=Count('event_id', filter=Q(depth__gte=300))
    ).order_by('date')

    agency_options = EarthquakeEvent.objects.exclude(agency__isnull=True).values_list('agency', flat=True).distinct().order_by('agency')

    context = {
        'events': events,
        'felt_events': felt_events,
        'stats': stats,
        'daily_stats': daily_stats,
        'agency_options': agency_options,
        'filters': request.GET,
    }
    return render(request, 'monitor/seismicity_analysis.html', context)