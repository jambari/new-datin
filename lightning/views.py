# lightning/views.py
import json
import calendar
from datetime import date, datetime, timedelta, timezone as dt_timezone
from django.utils import timezone
from django.shortcuts import render, redirect
from django.views import View
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.utils.dateparse import parse_date
from django.urls import reverse
import csv
import re
import os
import tempfile
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Strike, DailyStrikeSummary, LightningDataAvailability
import sqlite3
from django.db import transaction
from .forms import NexStormUploadForm


# ===============================================
# PAGE 1: DASHBOARD (Nexstorm Query)
# ===============================================

class NexStormQueryView(View):
    """ 
    Renders the Main Dashboard Page. 
    (The chart data is fetched via the API below)
    """
    def get(self, request, *args, **kwargs):
        return render(request, 'lightning/nexstorm_query_page.html')

class NexStormQueryAPIView(APIView):
    """
    API that provides the JSON data for the Dashboard Chart.
    """
    def get(self, request, *args, **kwargs):
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')

        # Default to last 30 days
        if not start_date_str or not end_date_str:
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=30)
        else:
            try:
                if isinstance(start_date_str, str):
                    start_date = parse_date(start_date_str)
                if isinstance(end_date_str, str):
                    end_date = parse_date(end_date_str)
            except (ValueError, TypeError):
                return Response({"error": "Invalid date format"}, status=status.HTTP_400_BAD_REQUEST)

        # Query Strike Summaries
        summaries = DailyStrikeSummary.objects.filter(
            summary_date__range=[start_date, end_date]
        ).order_by('summary_date')

        strike_data = []
        for s in summaries:
            strike_data.append({
                'date': s.summary_date.strftime('%Y-%m-%d'),
                'cg_plus': s.cg_plus_count,
                'cg_minus': s.cg_minus_count,
                'ic': s.ic_count,
                'other': s.other_count,
                'total': s.total_count
            })

        return Response({
            "strike_aggregation": strike_data
        })

# ===============================================
# PAGE 2: AVAILABILITY MATRIX (Input Data)
# ===============================================

@login_required
def lightning_availability_query(request):
    """
    Renders the Matrix Table page for inputting Availability data.
    """
    today = datetime.now()
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

    # DAFTAR STASIUN
    station_list = ['BBW 5 LD', 'BIK LD', 'JAY LD', 'MRK LD']

    start_date = date(selected_year, selected_month, 1)
    end_date = date(selected_year, selected_month, num_days)

    # Ambil data dari DB
    db_data_query = LightningDataAvailability.objects.filter(
        station__in=station_list,
        date__range=[start_date, end_date]
    ).values('station', 'date', 'percentage')

    data_map = {}
    for item in db_data_query:
        key = (item['station'], item['date'].strftime('%Y-%m-%d'))
        data_map[key] = item['percentage']

    # Bangun Tabel
    tabel_data = []
    for stasiun in station_list:
        row = {'nama': stasiun, 'hari': [], 'avg_row': 0}
        total_val = 0
        
        for d in list_tanggal:
            curr_date = date(selected_year, selected_month, d)
            date_str = curr_date.strftime('%Y-%m-%d')
            key = (stasiun, date_str)
            
            # Default value 100 jika tidak ada di DB
            val = 100.0 
            if key in data_map:
                val = data_map[key]
            
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
        'page_title': "Rekapitulasi Ketersediaan Data Lightning Detector",
        'sensor_name': "Lightning Detector",
        'sensor_type': 'lightning',
        'update_url': reverse('lightning:update_lightning_availability'), 
    }

    return render(request, 'lightning/lightning_availability_query.html', context)

@login_required
def update_lightning_availability(request):
    """ API to save data from the Availability Matrix page """
    try:
        data = json.loads(request.body)
        station = data.get('station')
        date_str = data.get('date')
        val = float(data.get('value', 0))

        LightningDataAvailability.objects.update_or_create(
            station=station,
            date=date_str,
            defaults={'percentage': val, 'channel': 'REPORT'}
        )
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

# ===============================================
# MAINTENANCE (Delete Data)
# ===============================================

class DeleteAllStrikesView(View):
    def post(self, request):
        Strike.objects.all().delete()
        DailyStrikeSummary.objects.all().delete()
        messages.success(request, "All strike data has been deleted.")
        return redirect('lightning:nexstorm_query_page')
    
class UploadNexStormView(View):
    template_name = 'lightning/upload_nexstorm.html'

    def get(self, request):
        form = NexStormUploadForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        # Gunakan getlist untuk mengambil semua file yang dipilih
        files = request.FILES.getlist('csv_file')
        
        # 1. VALIDASI JUMLAH FILE (MAX 7)
        if len(files) > 7:
            messages.error(request, f"Terlalu banyak file! Maksimal 7 file. Anda mengunggah {len(files)} file.")
            return redirect('lightning:upload_nexstorm')

        if not files:
            messages.error(request, "Tidak ada file yang dipilih.")
            return redirect('lightning:upload_nexstorm')

        processed_dates = []
        error_files = []

        # 2. LOOPING PROCESS UNTUK SETIAP FILE
        for uploaded_file in files:
            filename = uploaded_file.name
            
            # A. Parse Date dari Filename
            match = re.search(r'(\d{8})', filename)
            if not match:
                error_files.append(f"{filename} (Nama file tidak valid)")
                continue
            
            date_part = match.group(1)
            try:
                summary_date = datetime.strptime(date_part, '%Y%m%d').date()
            except ValueError:
                error_files.append(f"{filename} (Format tanggal salah)")
                continue

            # B. Simpan ke Temp File
            temp_csv_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.csv', mode='w+', encoding='utf-8') as temp_csv:
                    for chunk in uploaded_file.chunks():
                        temp_csv.write(chunk.decode('utf-8'))
                    temp_csv_path = temp_csv.name

                # C. Proses CSV (Panggil fungsi helper yang sama)
                self.process_csv_file(temp_csv_path, summary_date)
                processed_dates.append(str(summary_date))
            
            except Exception as e:
                error_files.append(f"{filename} (Error: {str(e)})")
            
            finally:
                # Bersihkan temp file setiap selesai 1 file
                if temp_csv_path and os.path.exists(temp_csv_path):
                    os.remove(temp_csv_path)

        # 3. BUAT LAPORAN HASIL
        if processed_dates:
            msg_success = f"Sukses memproses {len(processed_dates)} data tanggal: {', '.join(processed_dates)}."
            messages.success(request, msg_success)
        
        if error_files:
            msg_error = "Gagal memproses file berikut: " + "; ".join(error_files)
            messages.error(request, msg_error)

        return redirect('lightning:nexstorm_query_page')

    def process_csv_file(self, csv_path, summary_date):
        """
        Logic proses masih SAMA PERSIS dengan sebelumnya.
        Hanya dipanggil berulang kali dalam loop.
        """
        MIN_LAT = -3.014833
        MAX_LAT = -2.014833
        MIN_LON = 140.204667
        MAX_LON = 141.204667
        
        cg_plus = 0
        cg_minus = 0
        ic_count = 0
        other_count = 0
        total_filtered = 0

        strikes_buffer = []
        BATCH_SIZE = 1000

        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                reader.fieldnames = [name.strip() for name in reader.fieldnames]

            with transaction.atomic():
                for row in reader:
                    if not row.get('latitude') or not row.get('longitude') or not row.get('epoch_ms'):
                        continue

                    try:
                        epoch_ms = int(row['epoch_ms'])
                        lat_float = float(row['latitude'])
                        lon_float = float(row['longitude'])
                        type_int = int(row['type'])
                        
                        epoch_sec = epoch_ms / 1000.0
                        dt_utc = datetime.fromtimestamp(epoch_sec, tz=dt_timezone.utc)

                        strikes_buffer.append(Strike(
                            epoch_ms=epoch_ms,
                            timestamp=dt_utc,
                            latitude=lat_float,
                            longitude=lon_float,
                            strike_type=type_int
                        ))

                        if MIN_LAT <= lat_float <= MAX_LAT and MIN_LON <= lon_float <= MAX_LON:
                            total_filtered += 1
                            if type_int == 0:
                                cg_plus += 1
                            elif type_int == 1:
                                cg_minus += 1
                            elif type_int == 2:
                                ic_count += 1
                            else:
                                other_count += 1

                    except (ValueError, KeyError):
                        continue

                    if len(strikes_buffer) >= BATCH_SIZE:
                        Strike.objects.bulk_create(strikes_buffer, ignore_conflicts=True)
                        strikes_buffer = []

                if strikes_buffer:
                    Strike.objects.bulk_create(strikes_buffer, ignore_conflicts=True)

                DailyStrikeSummary.objects.update_or_create(
                    summary_date=summary_date,
                    defaults={
                        'cg_plus_count': cg_plus,
                        'cg_minus_count': cg_minus,
                        'ic_count': ic_count,
                        'other_count': other_count,
                        'total_count': total_filtered,
                    }
                )
        
        # Return tidak terlalu dibutuhkan di multi-file, tapi dibiarkan tidak masalah
        return True
    

class LightningInfographicView(View):
    template_name = 'lightning/infographic.html'

    def get(self, request):
        # Default ke hari ini
        end_date_str = request.GET.get('date')
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        else:
            end_date = datetime.now().date()

        # Hitung Start Date (7 hari termasuk end date)
        start_date = end_date - timedelta(days=6)

        # Ambil Data
        summaries = DailyStrikeSummary.objects.filter(
            summary_date__range=[start_date, end_date]
        ).order_by('summary_date')

        # Agregasi Data
        total_strikes = 0
        total_cg_plus = 0
        total_cg_minus = 0
        max_strike = 0
        max_date = "-"
        
        # Siapkan data untuk Chart JS
        chart_labels = []
        chart_data = []

        # Dictionary untuk akses cepat jika ada tanggal bolong
        data_dict = {s.summary_date: s for s in summaries}
        
        # Loop 7 hari pastikan urut
        current = start_date
        while current <= end_date:
            s = data_dict.get(current)
            val = s.total_count if s else 0
            
            # Chart Data
            chart_labels.append(current.strftime('%d %b')) # Format: 01 Oct
            chart_data.append(val)

            # Stats
            if s:
                total_strikes += s.total_count
                total_cg_plus += s.cg_plus_count
                total_cg_minus += s.cg_minus_count
                
                if s.total_count > max_strike:
                    max_strike = s.total_count
                    max_date = current.strftime('%d %B %Y')

            current += timedelta(days=1)

        context = {
            'end_date': end_date.strftime('%Y-%m-%d'),
            'display_date_range': f"{start_date.strftime('%d %b')} - {end_date.strftime('%d %b %Y')}",
            'total_strikes': total_strikes,
            'total_cg_plus': total_cg_plus,
            'total_cg_minus': total_cg_minus,
            'max_strike': max_strike,
            'max_date': max_date,
            'chart_labels': chart_labels,
            'chart_data': chart_data,
        }

        return render(request, self.template_name, context)