from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny 
from .models import WRSNGStatus, WRSNGDataAvailability
from .serializers import WRSNGStatusSerializer
from django.views.generic import ListView 
from django.utils.dateparse import parse_date 
from django.db.models import Q 
from django.utils import timezone 
import datetime # Import module datetime standard
import calendar
from collections import defaultdict
from django.views.decorators.http import require_POST
from django.urls import reverse
import json
from django.http import JsonResponse

class WRSNGStatusUpdateAPI(APIView):
    """
    API View untuk menerima data status WRSNG.
    Ini akan SELALU MEMBUAT entri log baru untuk setiap status yang diterima.
    """
    permission_classes = [AllowAny] 

    def post(self, request, *args, **kwargs):
        """
        Menerima data status WRSNG.
        """
        data = request.data
        
        serializer = WRSNGStatusSerializer(data=data)
        
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class WRSNGStatusListView(ListView):
    """
    Menampilkan daftar status WRSNG dengan paginasi dan filter.
    """
    model = WRSNGStatus
    template_name = 'wrsng/wrsng_status_list.html' 
    context_object_name = 'status_list' 
    paginate_by = 15 
    ordering = ['-status_datetime'] 

    def get_queryset(self):
        """
        Override queryset untuk menambahkan logika filter.
        """
        queryset = super().get_queryset()
        
        wrs_code_filter = self.request.GET.get('wrs_code', None)
        start_date_str = self.request.GET.get('start_date', None)
        end_date_str = self.request.GET.get('end_date', None)

        filters = Q()

        if wrs_code_filter and wrs_code_filter.strip() != '':
            filters &= Q(wrs_code__icontains=wrs_code_filter.strip())
            
        if start_date_str:
            start_date = parse_date(start_date_str)
            if start_date:
                # Correct usage: datetime.datetime.combine
                start_datetime_aware = timezone.make_aware(
                    datetime.datetime.combine(start_date, datetime.time.min)
                )
                filters &= Q(status_datetime__gte=start_datetime_aware)

        if end_date_str:
            end_date = parse_date(end_date_str)
            if end_date:
                # Correct usage: datetime.datetime.combine
                end_datetime_exclusive_aware = timezone.make_aware(
                    datetime.datetime.combine(end_date + datetime.timedelta(days=1), datetime.time.min)
                )
                filters &= Q(status_datetime__lt=end_datetime_exclusive_aware)

        return queryset.filter(filters)

    def get_context_data(self, **kwargs):
            context = super().get_context_data(**kwargs)
            
            # --- Ambil parameter filter yang sedang aktif ---
            # Kita simpan di context agar tidak hilang saat pindah halaman
            context['filter_wrs_code'] = self.request.GET.get('wrs_code', '')
            context['filter_start_date'] = self.request.GET.get('start_date', '')
            context['filter_end_date'] = self.request.GET.get('end_date', '')
            
            # Opsi dropdown
            context['wrs_code_options'] = WRSNGStatus.objects.values_list('wrs_code', flat=True).distinct().order_by('wrs_code')
            
            # --- LOGIKA PAGINASI BARU (ELIDED) ---
            # Ini membuat list halaman seperti: [1, 2, '...', 5, 6, 7, '...', 20]
            paginator = context.get('paginator')
            page = context.get('page_obj')
            
            if paginator and page:
                context['elided_page_range'] = paginator.get_elided_page_range(
                    page.number, 
                    on_each_side=2, 
                    on_ends=1
                )
                
            return context


@login_required
def wrsng_availability_query(request):
    today = datetime.datetime.now()
    try:
        selected_month = int(request.GET.get('month', today.month))
        selected_year = int(request.GET.get('year', today.year))
    except ValueError:
        selected_month = today.month
        selected_year = today.year

    _, num_days = calendar.monthrange(selected_year, selected_month)
    list_tanggal = list(range(1, num_days + 1))
    
    daftar_bulan_indo = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    month_name = daftar_bulan_indo[selected_month]

    station_list = [
        "Stageof Jayapura", "RRI Jayapura", "MAKO LANTAMAL X", "BPBD Kota Jayapura", 
        "BBMKG V Jayapura", "BPBD Provinsi Papua", "BASARNAS Papua", "BPBD Kab. Jayapura", 
        "BPBD Biak Numfor", "BPBD Waropen", "BASARNAS Merauke", "BPBD Kab. Mimika"
    ]

    # Date Range
    start_date = datetime.datetime(selected_year, selected_month, 1, tzinfo=datetime.timezone.utc)
    if selected_month == 12:
        next_month = datetime.datetime(selected_year + 1, 1, 1, tzinfo=datetime.timezone.utc)
    else:
        next_month = datetime.datetime(selected_year, selected_month + 1, 1, tzinfo=datetime.timezone.utc)
    
    # Range Tanggal Biasa (untuk query manual)
    start_date_date = start_date.date()
    end_date_date = (next_month - datetime.timedelta(seconds=1)).date()

    # 1. AMBIL DATA MANUAL (Editable)
    manual_data_query = WRSNGDataAvailability.objects.filter(
        station__in=station_list,
        date__range=[start_date_date, end_date_date],
        channel='REPORT'
    ).values('station', 'date', 'percentage')

    manual_map = {}
    for item in manual_data_query:
        # Format key: (station, day_integer)
        manual_map[(item['station'], item['date'].day)] = item['percentage']

    # 2. AMBIL DATA LOG (Otomatis)
    logs = WRSNGStatus.objects.filter(
        status_datetime__gte=start_date,
        status_datetime__lt=next_month,
        wrs_code__in=station_list
    ).values('wrs_code', 'status_datetime', 'display_status')

    auto_map = defaultdict(lambda: defaultdict(list))
    for log in logs:
        d_day = log['status_datetime'].day 
        code = log['wrs_code']
        status_val = log['display_status'] 
        auto_map[code][d_day].append(status_val)

    # 3. GABUNGKAN (Prioritas: Manual > Auto > Default 100)
    tabel_data = []
    for stasiun in station_list:
        row = {'nama': stasiun, 'hari': [], 'avg_row': 0}
        total_pct = 0
        
        for d in list_tanggal:
            val = 100.0 # Default Value 100 (Jika tidak ada data)

            # Cek Manual dulu
            if (stasiun, d) in manual_map:
                val = manual_map[(stasiun, d)]
            
            # Jika tidak ada manual, cek log otomatis
            elif stasiun in auto_map and d in auto_map[stasiun]:
                status_list = auto_map[stasiun][d]
                if status_list:
                    count_on = status_list.count(1)
                    count_total = len(status_list)
                    val = (count_on / count_total) * 100
            
            # Jika tidak ada keduanya, val tetap 100.0
            
            val = float(val)
            total_pct += val
            
            row['hari'].append({
                'day_num': d,
                'full_date': f"{selected_year}-{selected_month:02d}-{d:02d}", # Untuk ID update
                'val': val
            })
            
        row['avg_row'] = round(total_pct / num_days, 2)
        tabel_data.append(row)

    context = {
        'tabel_data': tabel_data,
        'list_tanggal': list_tanggal,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'month_name': month_name,
        'years_range': range(2020, 2030),
        'months_range': range(1, 13),
        'page_title': "Laporan Bulanan Availability WRSNG",
        'sensor_name': "WRS New Generation",
        'update_url': reverse('wrsng:update_wrsng_availability'), # URL AJAX
        'sensor_type': 'wrsng'
    }

    return render(request, 'wrsng/wrsng_availability_query.html', context)

# === API UPDATE ===
@require_POST
@login_required
def update_wrsng_availability(request):
    try:
        data = json.loads(request.body)
        station = data.get('station')
        date_str = data.get('date')
        val = float(data.get('value'))

        if val < 0 or val > 100:
            return JsonResponse({'status': 'error', 'message': 'Value 0-100'}, status=400)

        obj, created = WRSNGDataAvailability.objects.update_or_create(
            station=station,
            date=date_str,
            defaults={'percentage': val, 'channel': 'REPORT'}
        )

        return JsonResponse({'status': 'success', 'station': station, 'new_val': val})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)