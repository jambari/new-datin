# magnet/views.py
from django.contrib.auth.decorators import login_required
from .models import MagneticObservation, MagnetDataAvailability
from django.shortcuts import render, get_object_or_404,redirect
import json
from datetime import datetime
import math
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from .tasks import fill_external_form
import pytesseract
from PIL import Image
import re
import cv2  # Import OpenCV
import numpy as np # Import NumPy
from google.cloud import vision
import io
import os # Import modul os
from django.conf import settings
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView, DeleteView, DetailView
from django.contrib.gis.forms import PolygonField
from django.forms import ModelForm
from .models import Precursor
from django import forms
from repository.models import Gempa
from django.contrib.gis.geos import Point
from django.contrib import messages
from datetime import date
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.urls import reverse
import json
import calendar


# --- Helper Function for Conversion ---
def grad_to_dms(grad_str):
    """Converts a gradian value string to degrees, minutes, and seconds."""
    try:
        # Convert grad to decimal degrees: Degrees = Gradians * 0.9
        decimal_degrees = float(grad_str) * 0.9
        
        # Calculate degrees, minutes, and seconds
        degrees = int(decimal_degrees)
        minutes_float = (decimal_degrees - degrees) * 60
        minutes = int(minutes_float)
        seconds = round((minutes_float - minutes) * 60, 2) # round to 2 decimal places
        
        return {'deg': degrees, 'min': minutes, 'sec': seconds}
    except (ValueError, TypeError):
        return {'deg': 0, 'min': 0, 'sec': 0}

@login_required
def observation_form_view(request):
    # This logic runs for both GET and POST requests
    observer_names = ["Netty", "Lidya", "Jambari", "Berlian", "Achmad", "Alif", "Rivaldo"]
    sessions = ["Session 1", "Session 2"]
    
    if request.method == 'POST':
        # --- POST logic remains the same ---
        post_data = request.POST
        
        try:
            date_str = post_data.get('observation_date')
            observation_date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            observation_date_obj = None

        deklinasi_readings = ['WU', 'ED', 'WD', 'EU']
        inklinasi_readings = ['NU', 'SD', 'ND', 'SU']
        dek_readings = {r: {'hh': post_data.get(f'dek_{r.lower()}_hh'), 'mm': post_data.get(f'dek_{r.lower()}_mm'), 'ss': post_data.get(f'dek_{r.lower()}_ss'), 'circ': post_data.get(f'dek_{r.lower()}_circ')} for r in deklinasi_readings}
        ink_readings = {r: {'hh': post_data.get(f'ink_{r.lower()}_hh'), 'mm': post_data.get(f'ink_{r.lower()}_mm'), 'ss': post_data.get(f'ink_{r.lower()}_ss'), 'circ': post_data.get(f'ink_{r.lower()}_circ'), 'ftotal': post_data.get(f'ink_{r.lower()}_ftotal')} for r in inklinasi_readings}

        observation = MagneticObservation.objects.create(
            observation_date=observation_date_obj,
            observer=post_data.get('observer'),
            session=post_data.get('session'),
            cr_awal=post_data.get('cr_awal'),
            cl_awal=post_data.get('cl_awal'),
            cr_akhir=post_data.get('cr_akhir'),
            cl_akhir=post_data.get('cl_akhir'),
            meridian_1=post_data.get('meridian_1'),
            meridian_2=post_data.get('meridian_2'),
            deklinasi_readings=dek_readings,
            inklinasi_readings=ink_readings
        )

        converted_cr1_dms = grad_to_dms(observation.cr_awal)
        converted_cl1_dms = grad_to_dms(observation.cl_awal)
        converted_cr2_dms = grad_to_dms(observation.cr_akhir)
        converted_cl2_dms = grad_to_dms(observation.cl_akhir)
        
        converted_dek = {r: grad_to_dms(dek_readings[r]['circ']) for r in deklinasi_readings}
        converted_ink = {r: grad_to_dms(ink_readings[r]['circ']) for r in inklinasi_readings}
        
        request.session['selenium_data'] = {
            'pengamat': observation.observer,
            'datepicker': observation.observation_date.strftime('%Y-%m-%d'),
            'azimuth_tt': {'deg': 98, 'min': 45, 'sec': 31},
            'CR1': converted_cr1_dms,
            'CL1': converted_cl1_dms,
            'CR2': converted_cr2_dms,
            'CL2': converted_cl2_dms,
            'deklinasi_times': {r: f"{dek_readings[r]['hh']}:{dek_readings[r]['mm']}:{dek_readings[r]['ss']}" for r in deklinasi_readings},
            'deklinasi_dms': converted_dek,
            'inklinasi_times': {r: f"{ink_readings[r]['hh']}:{ink_readings[r]['mm']}:{ink_readings[r]['ss']}" for r in inklinasi_readings},
            'inklinasi_dms': converted_ink,
            'inklinasi_ftotals': {r: ink_readings[r]['ftotal'] for r in inklinasi_readings},
        }
        return redirect('conversion_result')

    # --- This context is for the GET request (loading a blank form) ---
    # It now includes all the default values for the template.
    context = {
        'observer_names': observer_names,
        'sessions': sessions,
        'cr_awal_default': 109.7,
        'cl_awal_default': 309.7,
        'cr_akhir_default': 109.7,
        'cl_akhir_default': 309.7,
        'deklinasi_data': [
            {'name': 'WU', 'default_circ': 302.6},
            {'name': 'ED', 'default_circ': 303.5},
            {'name': 'WD', 'default_circ': 103.7},
            {'name': 'EU', 'default_circ': 102.8},
        ],
        'inklinasi_data': [
            {'name': 'NU', 'default_circ': 175.7},
            {'name': 'SD', 'default_circ': 375.8},
            {'name': 'ND', 'default_circ': 224.6},
            {'name': 'SU', 'default_circ': 24.6},
        ]
    }
    return render(request, 'magnet/observation_form.html', context)


@login_required
def conversion_result_view(request):
    """A view to display the converted data before automation."""
    context = {
        'selenium_data': request.session.get('selenium_data', {})
    }
    return render(request, 'magnet/conversion_result.html', context)

@login_required
def observation_list_view(request):
    all_observations = MagneticObservation.objects.all().order_by('-observation_date') # Added ordering for consistency

    # Set the number of records per page
    paginator = Paginator(all_observations, 10)
    
    # Get the current page number from the URL
    page = request.GET.get('page')
    
    try:
        observations = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver the first page.
        observations = paginator.page(1)
    except EmptyPage:
        # If page is out of range, deliver the last page.
        observations = paginator.page(paginator.num_pages)

    context = {
        'observations': observations
    }
    return render(request, 'magnet/observation_list.html', context)


@login_required
def observation_detail_view(request, pk):
    observation = get_object_or_404(MagneticObservation, pk=pk)
    
    # --- NEW: Perform conversions for the detail page ---
    converted_data = {
        'cr_awal': grad_to_dms(observation.cr_awal),
        'cl_awal': grad_to_dms(observation.cl_awal),
        'cr_akhir': grad_to_dms(observation.cr_akhir),
        'cl_akhir': grad_to_dms(observation.cl_akhir),
        'deklinasi': {
            key: grad_to_dms(value.get('circ'))
            for key, value in observation.deklinasi_readings.items()
        },
        'inklinasi': {
            key: grad_to_dms(value.get('circ'))
            for key, value in observation.inklinasi_readings.items()
        },
    }
    
    context = {
        'observation': observation,
        'converted_data': converted_data, # Add converted data to context
    }
    return render(request, 'magnet/observation_detail.html', context)

@login_required
def trigger_automation_view(request):
    selenium_data = request.session.get('selenium_data', None)
    if selenium_data:
        # Send the job to the Celery worker
        fill_external_form.delay(selenium_data)
        # Redirect back to the records list
        return redirect('observation_list')
    else:
        # Handle case where there is no data
        return redirect('observation_form')
    

@login_required
def observation_edit_view(request, pk):
    observation = get_object_or_404(MagneticObservation, pk=pk)
    
    if request.method == 'POST':
        # --- This is the new logic to save the changes ---
        post_data = request.POST
        
        try:
            date_str = post_data.get('observation_date')
            observation.observation_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            observation.observation_date = None # Handle case where date is cleared
            
        # Update simple fields
        observation.observer = post_data.get('observer')
        observation.session = post_data.get('session')
        observation.cr_awal = post_data.get('cr_awal')
        observation.cl_awal = post_data.get('cl_awal')
        observation.cr_akhir = post_data.get('cr_akhir')
        observation.cl_akhir = post_data.get('cl_akhir')
        observation.meridian_1 = post_data.get('meridian_1')
        observation.meridian_2 = post_data.get('meridian_2')

        # Re-assemble the JSON data for readings
        deklinasi_readings = ['WU', 'ED', 'WD', 'EU']
        inklinasi_readings = ['NU', 'SD', 'ND', 'SU']

        observation.deklinasi_readings = {r: {'hh': post_data.get(f'dek_{r.lower()}_hh'), 'mm': post_data.get(f'dek_{r.lower()}_mm'), 'ss': post_data.get(f'dek_{r.lower()}_ss'), 'circ': post_data.get(f'dek_{r.lower()}_circ')} for r in deklinasi_readings}
        observation.inklinasi_readings = {r: {'hh': post_data.get(f'ink_{r.lower()}_hh'), 'mm': post_data.get(f'ink_{r.lower()}_mm'), 'ss': post_data.get(f'ink_{r.lower()}_ss'), 'circ': post_data.get(f'ink_{r.lower()}_circ'), 'ftotal': post_data.get(f'ink_{r.lower()}_ftotal')} for r in inklinasi_readings}

        # Save the updated object to the database
        observation.save()
        
        return redirect('observation_list')
        
    # This part for GET requests remains the same
    deklinasi_data = [{'name': k, 'data': v} for k, v in observation.deklinasi_readings.items()]
    inklinasi_data = [{'name': k, 'data': v} for k, v in observation.inklinasi_readings.items()]
        
    context = {
        'observation': observation,
        'observer_names': ["Netty", "Lidya", "Jambari", "Berlian", "Achmad", "Alif", "Rivaldo"],
        'sessions': ["Session 1", "Session 2"],
        'deklinasi_readings': ['WU', 'ED', 'WD', 'EU'], # Still needed for new form template compatibility
        'inklinasi_readings': ['NU', 'SD', 'ND', 'SU'], # Still needed for new form template compatibility
        'deklinasi_data': deklinasi_data,
        'inklinasi_data': inklinasi_data,
    }
    return render(request, 'magnet/observation_form_edit.html', context)

@login_required
def trigger_single_automation_view(request, pk):
    observation = get_object_or_404(MagneticObservation, pk=pk)

    # Re-create the data structure needed by the Selenium task
    # This uses the data already saved in the database
    selenium_data = {
        'pengamat': observation.observer,
        'datepicker': observation.observation_date.strftime('%Y-%m-%d'),
        'azimuth_tt': {'deg': 98, 'min': 45, 'sec': 31},
        'CR1': grad_to_dms(observation.cr_awal),
        'CL1': grad_to_dms(observation.cl_awal),
        'CR2': grad_to_dms(observation.cr_akhir),
        'CL2': grad_to_dms(observation.cl_akhir),
        'deklinasi_times': {r: f"{v['hh']}:{v['mm']}:{v['ss']}" for r, v in observation.deklinasi_readings.items()},
        'deklinasi_dms': {r: grad_to_dms(v['circ']) for r, v in observation.deklinasi_readings.items()},
        # Add Inklinasi data here if needed
        'inklinasi_times': {r: f"{v['hh']}:{v['mm']}:{v['ss']}" for r, v in observation.inklinasi_readings.items()},
        'inklinasi_dms': {r: grad_to_dms(v['circ']) for r, v in observation.inklinasi_readings.items()},
        'inklinasi_ftotals': {r: v['ftotal'] for r, v in observation.inklinasi_readings.items()},
        
    }

    # Trigger the background task
    fill_external_form.delay(selenium_data)

    # Redirect back to the list
    return redirect('observation_list')

@login_required
def observation_delete_view(request, pk):
    observation = get_object_or_404(MagneticObservation, pk=pk)
    if request.method == 'POST':
        observation.delete()
        return redirect('observation_list')

    context = {
        'observation': observation
    }
    return render(request, 'magnet/observation_confirm_delete.html', context)

def dim_calculator_view(request):
    """
    Menampilkan halaman kalkulator DIM untuk input manual.
    """
    # Buat list label di sini
    deklinasi_labels = ['wu', 'ed', 'wd', 'eu']
    
    # Kirim list tersebut ke template melalui context
    context = {
        'deklinasi_labels': deklinasi_labels
    }
    
    return render(request, 'magnet/dim_calculator.html', context)

class PrecursorForm(forms.ModelForm):
    
    def __init__(self, *args, **kwargs):
        """
        Menambahkan nilai awal (default) untuk field magnitude_tolerance.
        """
        super().__init__(*args, **kwargs)
        # Set nilai default hanya saat membuat objek baru (instance belum ada)
        if not self.instance.pk:
            self.fields['magnitude_tolerance'].initial = 0.2

    class Meta:
        model = Precursor
        fields = [
            'anomaly_timestamp', 'predicted_start_date', 'predicted_end_date',
            'predicted_magnitude', 'magnitude_tolerance', 'location_description',
            'location_polygon', 'azimuth',
        ]
        widgets = {
            'anomaly_timestamp': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'predicted_start_date': forms.DateInput(attrs={'type': 'date'}),
            'predicted_end_date': forms.DateInput(attrs={'type': 'date'}),
            'azimuth': forms.NumberInput(attrs={'step': '0.1', 'min': '0', 'max': '360', 'placeholder': 'Contoh: 125.2'}),
            'location_polygon': forms.Textarea(attrs={'hidden': True}),
        }


class PrecursorCreateView(CreateView):
    """View untuk membuat entri prekursor baru."""
    model = Precursor
    form_class = PrecursorForm
    template_name = 'magnet/precursor_form.html'
    success_url = reverse_lazy('precursor_list') # Arahkan ke halaman rekap setelah berhasil

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Tambah Prekursor Baru"
        return context

class PrecursorUpdateView(UpdateView):
    """View untuk mengedit entri prekursor yang sudah ada."""
    model = Precursor
    form_class = PrecursorForm
    template_name = 'magnet/precursor_form.html' # Menggunakan template form yang sama
    success_url = reverse_lazy('precursor_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Edit Prekursor"
        return context

# === TAMBAHKAN VIEW BARU UNTUK HAPUS ===
class PrecursorDeleteView(DeleteView):
    """View untuk menghapus entri prekursor."""
    model = Precursor
    template_name = 'magnet/precursor_confirm_delete.html' # Template konfirmasi baru
    success_url = reverse_lazy('precursor_list')

# SummaryView tidak berubah
class SummaryView(ListView):
    model = Precursor
    template_name = 'magnet/summary.html'
    context_object_name = 'precursors_list'
    ordering = ['-created_at']
    paginate_by = 10  # Menambahkan paginasi

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        total_count = Precursor.objects.count()
        validated_count = Precursor.objects.filter(is_validated=True).count()
        accuracy = (validated_count / total_count * 100) if total_count > 0 else 0
        
        context['title'] = "Rekapitulasi Validasi Prekursor"
        context['total_precursors'] = total_count
        context['validated_precursors'] = validated_count
        context['accuracy_percentage'] = round(accuracy, 2)
        return context

# === VIEW BARU UNTUK HALAMAN DETAIL ===
class PrecursorDetailView(DetailView):
    model = Precursor
    template_name = 'magnet/precursor_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        precursor = self.get_object()
        
        # Mengubah poligon menjadi format GeoJSON untuk Leaflet
        if precursor.location_polygon:
            context['polygon_geojson'] = precursor.location_polygon.geojson
        else:
            context['polygon_geojson'] = 'null'
            
        # Menyiapkan data gempa jika ada
        earthquake_data = None
        if precursor.validating_earthquake:
            eq = precursor.validating_earthquake
            earthquake_data = {
                'lat': float(eq.latitude),
                'lon': float(eq.longitude),
                'magnitudo': float(eq.magnitudo),
                'depth': eq.depth,
                'time': eq.origin_datetime.strftime('%d %b %Y, %H:%M:%S UTC'),
            }
        
        # Mengubah data gempa menjadi string JSON
        context['earthquake_data_json'] = json.dumps(earthquake_data)
        
        context['title'] = f"Detail Prekursor ID: {precursor.id}"
        return context

# === TAMBAHKAN VIEW BARU UNTUK VALIDASI SATUAN ===
def validate_single_precursor(request, pk):
    precursor = get_object_or_404(Precursor, pk=pk)
    
    min_mag = precursor.predicted_magnitude - precursor.magnitude_tolerance
    max_mag = precursor.predicted_magnitude + precursor.magnitude_tolerance
    
    potential_gempas = Gempa.objects.filter(
        origin_datetime__date__gte=precursor.predicted_start_date,
        origin_datetime__date__lte=precursor.predicted_end_date,
        magnitudo__gte=max(5.0, min_mag),
        magnitudo__lte=max_mag
    )
    
    matching_gempa = None
    if precursor.location_polygon:
        for gempa in potential_gempas:
            if gempa.longitude is not None and gempa.latitude is not None:
                gempa_point = Point(float(gempa.longitude), float(gempa.latitude), srid=4326)
                if gempa_point.within(precursor.location_polygon):
                    matching_gempa = gempa
                    break
    
    if matching_gempa:
        precursor.is_validated = True
        precursor.validating_earthquake = matching_gempa
        precursor.save()
        messages.success(request, f"Prekursor ID {precursor.id} berhasil divalidasi oleh gempa: M{matching_gempa.magnitudo}")
    else:
        # Logika jika tidak ada gempa yang cocok
        precursor.is_validated = False
        precursor.validating_earthquake = None
        precursor.save()
        
        today = date.today()
        if today > precursor.predicted_end_date:
            messages.warning(request, f"Validasi gagal: Rentang waktu untuk Prekursor ID {precursor.id} telah berakhir tanpa ada gempa yang cocok.")
        else:
            messages.info(request, f"Tidak ditemukan gempa yang cocok untuk memvalidasi Prekursor ID {precursor.id} saat ini.")
            
    return redirect('precursor_list')

@login_required
def magnet_availability_query(request):
    """
    View untuk menampilkan matriks availability Magnetometer.
    Menggunakan template KHUSUS: magnet/magnet_availability_query.html
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

    # DAFTAR STASIUN MAGNET (Sesuaikan dengan kebutuhan)
    # Berdasarkan screenshot Anda (JYP_P, JYP_V)
    station_list = [
        'JYP_P', 'JYP_V'
    ]

    start_date = date(selected_year, selected_month, 1)
    end_date = date(selected_year, selected_month, num_days)

    # Ambil data dari DB
    db_data_query = MagnetDataAvailability.objects.filter(
        station__in=station_list,
        date__range=[start_date, end_date]
    ).values('station', 'date', 'percentage')

    data_map = {}
    for item in db_data_query:
        key = (item['station'], item['date'].strftime('%Y-%m-%d'))
        data_map[key] = item['percentage']

    # Bangun Struktur Tabel
    tabel_data = []
    for stasiun in station_list:
        row = {'nama': stasiun, 'hari': [], 'avg_row': 0}
        total_val = 0
        
        for d in list_tanggal:
            curr_date = date(selected_year, selected_month, d)
            date_str = curr_date.strftime('%Y-%m-%d')
            key = (stasiun, date_str)
            
            # Default value 100 jika tidak ada di DB (sama seperti lightning)
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
        
        'page_title': "Rekapitulasi Persentasi Hasil Monitoring Ketersediaan Data Magnet",
        'sensor_name': "Magnetometer",
        'sensor_type': 'magnet',
        # URL API update spesifik untuk magnet
        'update_url': reverse('update_magnet_availability'), 
    }

    # Render template khusus yang ada di folder magnet
    return render(request, 'magnet/magnet_availability_query.html', context)


@require_POST
@login_required
def update_magnet_availability(request):
    """
    API AJAX khusus untuk menyimpan data Magnet.
    """
    try:
        data = json.loads(request.body)
        station = data.get('station')
        date_str = data.get('date')
        val = float(data.get('value'))

        if val < 0 or val > 100:
            return JsonResponse({'status': 'error', 'message': 'Value must be 0-100'}, status=400)

        # Update or Create
        obj, created = MagnetDataAvailability.objects.update_or_create(
            station=station,
            date=date_str,
            defaults={
                'percentage': val,
                'channel': 'REPORT'
            }
        )

        return JsonResponse({
            'status': 'success', 
            'station': station, 
            'new_val': val
        })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)