# magnet/views.py
from django.contrib.auth.decorators import login_required
from .models import MagneticObservation, MagnetDataAvailability
from django.shortcuts import render, get_object_or_404,redirect
import csv
from django.http import HttpResponse
from django.utils.dateparse import parse_date
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
from decimal import Decimal

def clean_decimal_input(val):
    if val in [None, '', 'None']:
        return None
    try:
        return float(str(val).replace('°', '').strip())
    except:
        return None

def dms_to_dec(d, m, s):
    """Mengubah input deg, min, sec dari form HTML menjadi nilai desimal untuk Database"""
    try:
        d_val = float(d) if d else 0.0
        m_val = float(m) if m else 0.0
        s_val = float(s) if s else 0.0
        
        sign = -1 if d_val < 0 else 1
        return sign * (abs(d_val) + (m_val / 60.0) + (s_val / 3600.0))
    except (ValueError, TypeError):
        return None

def dec_to_dms(decimal_val):
    """Memecah nilai desimal kembali menjadi Derajat, Menit, Detik untuk form Edit"""
    if decimal_val is None or str(decimal_val).strip() == '':
        return {'deg': '', 'min': '', 'sec': ''}
    try:
        abs_val = abs(float(decimal_val))
        d = int(abs_val)
        
        # Kalkulasi presisi tinggi agar tidak terjadi bug 59.9999
        remainder = (abs_val - d) * 60.0
        m = int(remainder)
        s = round((remainder - m) * 60.0, 1)
        
        if s >= 60:
            s = 0.0
            m += 1
        if m >= 60:
            m = 0
            d += 1
            
        if float(decimal_val) < 0:
            d = -d
        return {'deg': d, 'min': m, 'sec': s}
    except (ValueError, TypeError):
        return {'deg': '', 'min': '', 'sec': ''}
    
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
    observer_names = ["Netty", "Lidya", "Jambari", "Berlian", "Achmad", "Alif", "Rivaldo", "Donny", "Anas", "Richard", "Juan"]
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
def observation_list_view(request, filter_type=None):
    all_observations = MagneticObservation.objects.all().order_by('-observation_date')

    # Filter by instrument type if specified
    if filter_type == 'bartington':
        # Bartington records have 'deg' key in deklinasi_readings JSON
        all_observations = all_observations.filter(deklinasi_readings__WU__has_key='deg')
        page_title = "Magnetic Observation Records — Bartington (Deg)"
    elif filter_type == 'mingeo':
        # MinGeo records have 'circ' key in deklinasi_readings JSON
        all_observations = all_observations.filter(deklinasi_readings__WU__has_key='circ')
        page_title = "Magnetic Observation Records — MinGeo (Grad)"
    else:
        page_title = "Magnetic Observation Records"

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
        'observations': observations,
        'page_title': page_title,
        'filter_type': filter_type,
    }
    return render(request, 'magnet/observation_list.html', context)


@login_required
def observation_detail_view(request, pk):
    observation = get_object_or_404(MagneticObservation, pk=pk)
    
    # Detect record type using the model property
    is_bartington = observation.is_bartington

    if is_bartington:
        dek = observation.deklinasi_readings or {}
        # Full DMS for titik tetap is stored under underscore-prefixed keys
        def tt_dms(key):
            d = dek.get(key, {})
            return {'deg': int(d.get('deg', 0)), 'min': int(d.get('min', 0)), 'sec': d.get('sec', 0)}

        converted_data = {
            'cr_awal':  tt_dms('_cr_awal'),
            'cl_awal':  tt_dms('_cl_awal'),
            'cr_akhir': tt_dms('_cr_akhir'),
            'cl_akhir': tt_dms('_cl_akhir'),
            'deklinasi': {
                key: {'deg': int(val.get('deg', 0)), 'min': int(val.get('min', 0)), 'sec': val.get('sec', 0)}
                for key, val in dek.items() if not key.startswith('_')
            },
            'inklinasi': {
                key: {'deg': int(val.get('deg', 0)), 'min': int(val.get('min', 0)), 'sec': val.get('sec', 0)}
                for key, val in (observation.inklinasi_readings or {}).items()
            },
        }
    else:
        # MinGeo records store gradians — convert to DMS
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
        'converted_data': converted_data,
        'meridian_1_dms': dec_to_dms(observation.meridian_1),
        'meridian_2_dms': dec_to_dms(observation.meridian_2),
    }
    return render(request, 'magnet/observation_detail.html', context)

@login_required
def trigger_automation_view(request):
    selenium_data = request.session.get('selenium_data', None)
    if selenium_data:
        # Send the job to the Celery worker
        fill_external_form.delay(selenium_data)
        # Redirect back to the records list
        return redirect('observation_list_bartington')
    else:
        # Handle case where there is no data
        return redirect('observation_form')
    

@login_required
def observation_edit_view(request, pk):
    observation = get_object_or_404(MagneticObservation, pk=pk)

    # ================================
    # HELPER (WAJIB ADA)
    # ================================
    def clean_decimal_input(val):
        if val in [None, '', 'None']:
            return None
        try:
            return Decimal(str(val).replace('°', '').strip())
        except:
            return None

    def clean_float(val):
        if val in [None, '', 'None']:
            return 0.0
        try:
            return float(str(val).replace('°', '').strip())
        except:
            return 0.0

    # ==========================================
    # 1. POST Logic
    # ==========================================
    if request.method == 'POST':
        post_data = request.POST

        # DATE
        try:
            observation.observation_date = datetime.strptime(
                post_data.get('observation_date'), '%Y-%m-%d'
            ).date()
        except:
            observation.observation_date = None

        is_bart = 'cr_awal_deg' in post_data

        # ================================
        # TITIK TETAP
        # ================================
        if is_bart:
            observation.cr_awal = dms_to_dec(
                post_data.get('cr_awal_deg'),
                post_data.get('cr_awal_min'),
                post_data.get('cr_awal_sec')
            )
            observation.cl_awal = dms_to_dec(
                post_data.get('cl_awal_deg'),
                post_data.get('cl_awal_min'),
                post_data.get('cl_awal_sec')
            )
            observation.cr_akhir = dms_to_dec(
                post_data.get('cr_akhir_deg'),
                post_data.get('cr_akhir_min'),
                post_data.get('cr_akhir_sec')
            )
            observation.cl_akhir = dms_to_dec(
                post_data.get('cl_akhir_deg'),
                post_data.get('cl_akhir_min'),
                post_data.get('cl_akhir_sec')
            )
        else:
            observation.cr_awal = clean_decimal_input(post_data.get('cr_awal'))
            observation.cl_awal = clean_decimal_input(post_data.get('cl_awal'))
            observation.cr_akhir = clean_decimal_input(post_data.get('cr_akhir'))
            observation.cl_akhir = clean_decimal_input(post_data.get('cl_akhir'))

        # ================================
        # FIELD BIASA
        # ================================
        observation.observer = post_data.get('observer')
        observation.session = post_data.get('session')
        observation.meridian_1 = clean_decimal_input(post_data.get('meridian_1'))
        observation.meridian_2 = clean_decimal_input(post_data.get('meridian_2'))

        dek_keys = ['WU', 'ED', 'WD', 'EU']
        ink_keys = ['NU', 'SD', 'ND', 'SU']

        # ================================
        # BARTINGTON
        # ================================
        if is_bart:
            observation.deklinasi_readings = {
                r: {
                    'hh': clean_float(post_data.get(f'dek_{r.lower()}_hh')),
                    'mm': clean_float(post_data.get(f'dek_{r.lower()}_mm')),
                    'ss': clean_float(post_data.get(f'dek_{r.lower()}_ss')),
                    'deg': clean_float(post_data.get(f'dek_{r.lower()}_deg')),
                    'min': clean_float(post_data.get(f'dek_{r.lower()}_min')),
                    'sec': clean_float(post_data.get(f'dek_{r.lower()}_sec')),
                }
                for r in dek_keys
            }

            observation.inklinasi_readings = {
                r: {
                    'hh': clean_float(post_data.get(f'ink_{r.lower()}_hh')),
                    'mm': clean_float(post_data.get(f'ink_{r.lower()}_mm')),
                    'ss': clean_float(post_data.get(f'ink_{r.lower()}_ss')),
                    'deg': clean_float(post_data.get(f'ink_{r.lower()}_deg')),
                    'min': clean_float(post_data.get(f'ink_{r.lower()}_min')),
                    'sec': clean_float(post_data.get(f'ink_{r.lower()}_sec')),
                    'ftotal': clean_float(post_data.get(f'ink_{r.lower()}_ftotal')),
                }
                for r in ink_keys
            }

        # ================================
        # MINGEO
        # ================================
        else:
            observation.deklinasi_readings = {
                r: {
                    'hh': clean_float(post_data.get(f'dek_{r.lower()}_hh')),
                    'mm': clean_float(post_data.get(f'dek_{r.lower()}_mm')),
                    'ss': clean_float(post_data.get(f'dek_{r.lower()}_ss')),
                    'circ': clean_float(post_data.get(f'dek_{r.lower()}_circ')),
                }
                for r in dek_keys
            }

            observation.inklinasi_readings = {
                r: {
                    'hh': clean_float(post_data.get(f'ink_{r.lower()}_hh')),
                    'mm': clean_float(post_data.get(f'ink_{r.lower()}_mm')),
                    'ss': clean_float(post_data.get(f'ink_{r.lower()}_ss')),
                    'circ': clean_float(post_data.get(f'ink_{r.lower()}_circ')),
                    'ftotal': clean_float(post_data.get(f'ink_{r.lower()}_ftotal')),
                }
                for r in ink_keys
            }

        # BIARKAN MODEL HITUNG SENDIRI
        observation.save()

        return redirect('observation_list')

    # ==========================================
    # 2. GET Logic (TIDAK DIUBAH)
    # ==========================================
    observer_names = ["Netty", "Lidya", "Jambari", "Berlian", "Achmad", "Alif", "Rivaldo", "Donny", "Anas", "Richard", "Juan"]
    sessions = ["Session 1", "Session 2", "Session 3"]

    context = {
        'observation': observation,
        'observer_names': observer_names,
        'sessions': sessions,
    }

    if observation.is_bartington:
        dek = observation.deklinasi_readings or {}

        def get_tt(key):
            d = dek.get(key, {})
            return {
                'deg': '' if d.get('deg') in [None, 'None'] else d.get('deg'),
                'min': '' if d.get('min') in [None, 'None'] else d.get('min'),
                'sec': '' if d.get('sec') in [None, 'None'] else d.get('sec'),
            }

        context['cr_awal_default'] = get_tt('_cr_awal')
        context['cl_awal_default'] = get_tt('_cl_awal')
        context['cr_akhir_default'] = get_tt('_cr_akhir')
        context['cl_akhir_default'] = get_tt('_cl_akhir')

        def clean_val(v):
            return '' if v is None or str(v).strip() in ['', 'None'] else v

        dek_data = []
        for name in ['WU', 'ED', 'WD', 'EU']:
            val = observation.deklinasi_readings.get(name, {}) if observation.deklinasi_readings else {}
            deg = clean_val(val.get('deg'))
            min_val = clean_val(val.get('min'))
            sec_val = clean_val(val.get('sec'))

            if deg != '':
                if min_val == '': min_val = 0
                if sec_val == '': sec_val = 0

            dek_data.append({
                'name': name,
                'hh': clean_val(val.get('hh')),
                'mm': clean_val(val.get('mm')),
                'ss': clean_val(val.get('ss')),
                'deg': deg,
                'min': min_val,
                'sec': sec_val
            })

        context['deklinasi_data'] = dek_data

        ink_data = []
        for name in ['NU', 'SD', 'ND', 'SU']:
            val = observation.inklinasi_readings.get(name, {}) if observation.inklinasi_readings else {}

            ink_data.append({
                'name': name,
                'hh': clean_val(val.get('hh')),
                'mm': clean_val(val.get('mm')),
                'ss': clean_val(val.get('ss')),
                'deg': clean_val(val.get('deg')),
                'min': clean_val(val.get('min')),
                'sec': clean_val(val.get('sec')),
                'ftotal': clean_val(val.get('ftotal'))
            })

        context['inklinasi_data'] = ink_data

        return render(request, 'magnet/observation_bartington_form_edit.html', context)

    else:
        context['deklinasi_data'] = [{'name': k, 'data': v} for k, v in observation.deklinasi_readings.items()]
        context['inklinasi_data'] = [{'name': k, 'data': v} for k, v in observation.inklinasi_readings.items()]
        return render(request, 'magnet/observation_form_edit.html', context)

@login_required
def trigger_single_automation_view(request, pk):
    """Prepares and triggers the Celery task for an existing record."""
    observation = get_object_or_404(MagneticObservation, pk=pk)

    # Helper to check if record is Bartington (has 'deg') or MinGeo (needs 'grad_to_dms')
    def get_dms(data_dict):
        if 'deg' in data_dict:
            # Data is already in DMS format
            return {
                'deg': data_dict.get('deg', 0), 
                'min': data_dict.get('min', 0), 
                'sec': data_dict.get('sec', 0)
            }
        # Data is in Gradian format, needs conversion
        return grad_to_dms(data_dict.get('circ', 0))

    # Re-create the data structure needed by the Selenium task
    selenium_data = {
        'pengamat': observation.observer,
        'datepicker': observation.observation_date.strftime('%Y-%m-%d'),
        'azimuth_tt': {'deg': 98, 'min': 45, 'sec': 31},
        
        # Fix marks conversion
        'CR1': get_dms({'circ': observation.cr_awal}) if not hasattr(observation.deklinasi_readings.get('WU'), 'deg') else {'deg': observation.cr_awal, 'min':0, 'sec':0},
        'CL1': get_dms({'circ': observation.cl_awal}) if not hasattr(observation.deklinasi_readings.get('WU'), 'deg') else {'deg': observation.cl_awal, 'min':0, 'sec':0},
        'CR2': get_dms({'circ': observation.cr_akhir}) if not hasattr(observation.deklinasi_readings.get('WU'), 'deg') else {'deg': observation.cr_akhir, 'min':0, 'sec':0},
        'CL2': get_dms({'circ': observation.cl_akhir}) if not hasattr(observation.deklinasi_readings.get('WU'), 'deg') else {'deg': observation.cl_akhir, 'min':0, 'sec':0},
        
        # PERBAIKAN: Gunakan if isinstance(v, dict) dan .get() yang aman beserta .zfill(2) agar formatnya 00:00:00
        'deklinasi_times': {
            r: f"{str(v.get('hh', '00')).zfill(2)}:{str(v.get('mm', '00')).zfill(2)}:{str(v.get('ss', '00')).zfill(2)}" 
            for r, v in observation.deklinasi_readings.items() if isinstance(v, dict) and not r.startswith('_')
        },
        'deklinasi_dms': {
            r: get_dms(v) 
            for r, v in observation.deklinasi_readings.items() if isinstance(v, dict) and not r.startswith('_')
        },
        
        'inklinasi_times': {
            r: f"{str(v.get('hh', '00')).zfill(2)}:{str(v.get('mm', '00')).zfill(2)}:{str(v.get('ss', '00')).zfill(2)}" 
            for r, v in observation.inklinasi_readings.items() if isinstance(v, dict) and not r.startswith('_')
        },
        'inklinasi_dms': {
            r: get_dms(v) 
            for r, v in observation.inklinasi_readings.items() if isinstance(v, dict) and not r.startswith('_')
        },
        'inklinasi_ftotals': {
            r: v.get('ftotal', 0) 
            for r, v in observation.inklinasi_readings.items() if isinstance(v, dict) and not r.startswith('_')
        },
    }

    # Trigger the background Celery task
    fill_external_form.delay(selenium_data)

    messages.success(request, f"Automation task started for ID {pk}. You can check the screenshot results in the app folder.")
    return redirect('observation_list_bartington')

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


# magnet/views.py

@login_required
def observation_bartington_form_view(request):
    """Specific view for Bartington (Degrees) using dedicated template."""
    observer_names = ["Lidya", "Jambari", "Berlian", "Achmad", "Alif", "Rivaldo", "Donny", "Anas", "Richard", "Juan"]
    sessions = ["Session 1", "Session 2"]
    
    if request.method == 'POST':
        post_data = request.POST
        
        # 1. FIX ATTRIBUTE ERROR: Convert date string to object
        try:
            date_str = post_data.get('observation_date')
            if not date_str:
                raise ValueError("Tanggal kosong")
            observation_date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            # Cegah aplikasi crash, kembalikan user ke form dengan pesan error
            messages.error(request, "Tanggal observasi wajib diisi dengan format yang benar.")
            return redirect('observation_bartington')

        # 2. FIX VALIDATION ERROR: Helper for empty decimals
        def clean_dec(val):
            if val is None or str(val).strip() == "":
                return 0.0
            try:
                # Remove any unit symbols like '°' before converting
                clean_val = str(val).replace('°', '').strip()
                return float(clean_val)
            except ValueError:
                return 0.0

        # Create the observation record
        observation = MagneticObservation.objects.create(
            observation_date=observation_date_obj,
            observer=post_data.get('observer'),
            session=post_data.get('session'),
            cr_awal=clean_dec(post_data.get('cr_awal_deg')),
            cl_awal=clean_dec(post_data.get('cl_awal_deg')),
            cr_akhir=clean_dec(post_data.get('cr_akhir_deg')),
            cl_akhir=clean_dec(post_data.get('cl_akhir_deg')),
            meridian_1=clean_dec(post_data.get('meridian_1')),
            meridian_2=clean_dec(post_data.get('meridian_2')),
            deklinasi_readings={
                **{r: {
                    'hh': post_data.get(f'dek_{r.lower()}_hh'),
                    'mm': post_data.get(f'dek_{r.lower()}_mm'),
                    'ss': post_data.get(f'dek_{r.lower()}_ss'),
                    'deg': clean_dec(post_data.get(f'dek_{r.lower()}_deg')),
                    'min': clean_dec(post_data.get(f'dek_{r.lower()}_min')),
                    'sec': clean_dec(post_data.get(f'dek_{r.lower()}_sec')),
                } for r in ['WU', 'ED', 'WD', 'EU']},
                # Store full DMS for titik tetap so detail view can display them correctly
                '_cr_awal':  {'deg': clean_dec(post_data.get('cr_awal_deg')),  'min': clean_dec(post_data.get('cr_awal_min')),  'sec': clean_dec(post_data.get('cr_awal_sec'))},
                '_cl_awal':  {'deg': clean_dec(post_data.get('cl_awal_deg')),  'min': clean_dec(post_data.get('cl_awal_min')),  'sec': clean_dec(post_data.get('cl_awal_sec'))},
                '_cr_akhir': {'deg': clean_dec(post_data.get('cr_akhir_deg')), 'min': clean_dec(post_data.get('cr_akhir_min')), 'sec': clean_dec(post_data.get('cr_akhir_sec'))},
                '_cl_akhir': {'deg': clean_dec(post_data.get('cl_akhir_deg')), 'min': clean_dec(post_data.get('cl_akhir_min')), 'sec': clean_dec(post_data.get('cl_akhir_sec'))},
            },
            inklinasi_readings={r: {
                'hh': post_data.get(f'ink_{r.lower()}_hh'),
                'mm': post_data.get(f'ink_{r.lower()}_mm'),
                'ss': post_data.get(f'ink_{r.lower()}_ss'),
                'deg': clean_dec(post_data.get(f'ink_{r.lower()}_deg')),
                'min': clean_dec(post_data.get(f'ink_{r.lower()}_min')),
                'sec': clean_dec(post_data.get(f'ink_{r.lower()}_sec')),
                'ftotal': clean_dec(post_data.get(f'ink_{r.lower()}_ftotal'))
            } for r in ['NU', 'SD', 'ND', 'SU']}
        )

        # Map DMS directly for Selenium automation session
        request.session['selenium_data'] = {
            'pengamat': observation.observer,
            'datepicker': observation.observation_date.strftime('%Y-%m-%d'), # Now works!
            'azimuth_tt': {'deg': 98, 'min': 45, 'sec': 31},
            'CR1': {'deg': post_data.get('cr_awal_deg'), 'min': post_data.get('cr_awal_min'), 'sec': post_data.get('cr_awal_sec')},
            'CL1': {'deg': post_data.get('cl_awal_deg'), 'min': post_data.get('cl_awal_min'), 'sec': post_data.get('cl_awal_sec')},
            'CR2': {'deg': post_data.get('cr_akhir_deg'), 'min': post_data.get('cr_akhir_min'), 'sec': post_data.get('cr_akhir_sec')},
            'CL2': {'deg': post_data.get('cl_akhir_deg'), 'min': post_data.get('cl_akhir_min'), 'sec': post_data.get('cl_akhir_sec')},
            'deklinasi_times': {r: f"{post_data.get(f'dek_{r.lower()}_hh')}:{post_data.get(f'dek_{r.lower()}_mm')}:{post_data.get(f'dek_{r.lower()}_ss')}" for r in ['WU', 'ED', 'WD', 'EU']},
            'deklinasi_dms': {r: {
                'deg': post_data.get(f'dek_{r.lower()}_deg'), 'min': post_data.get(f'dek_{r.lower()}_min'), 'sec': post_data.get(f'dek_{r.lower()}_sec')
            } for r in ['WU', 'ED', 'WD', 'EU']},
            'inklinasi_times': {r: f"{post_data.get(f'ink_{r.lower()}_hh')}:{post_data.get(f'ink_{r.lower()}_mm')}:{post_data.get(f'ink_{r.lower()}_ss')}" for r in ['NU', 'SD', 'ND', 'SU']},
            'inklinasi_dms': {r: {
                'deg': post_data.get(f'ink_{r.lower()}_deg'), 'min': post_data.get(f'ink_{r.lower()}_min'), 'sec': post_data.get(f'ink_{r.lower()}_sec')
            } for r in ['NU', 'SD', 'ND', 'SU']},
            'inklinasi_ftotals': {r: post_data.get(f'ink_{r.lower()}_ftotal') for r in ['NU', 'SD', 'ND', 'SU']},
        }
        return redirect('conversion_result')

    # Default context for GET request
    context = {
        'observer_names': observer_names,
        'sessions': sessions,
        'is_bartington': True,
        'unit_label': 'deg',
        'cr_awal_default': {'deg': 98, 'min': 45, 'sec': 31},
        'cl_awal_default': {'deg': 278, 'min': 45, 'sec': 31},
        'deklinasi_data': [
            {'name': 'WU', 'deg': 272, 'min': "", 'sec': ""},
            {'name': 'ED', 'deg': 273, 'min': "", 'sec': ""},
            {'name': 'WD', 'deg': 93, 'min': "", 'sec': ""},
            {'name': 'EU', 'deg': 92, 'min': "", 'sec': ""},
        ],
        'inklinasi_data': [
            {'name': 'NU', 'deg': 158, 'min': "", 'sec': ""},
            {'name': 'SD', 'deg': 338, 'min': "", 'sec': ""},
            {'name': 'ND', 'deg': 202, 'min': "", 'sec': ""},
            {'name': 'SU', 'deg': 22, 'min': "", 'sec': ""},
        ]
    }
    return render(request, 'magnet/observation_bartington_form.html', context)

def observation_legacy_list_view(request):
    """
    Menampilkan khusus data observasi historis (Legacy Data) hasil import Excel,
    dilengkapi dengan filter Date Range dan fitur Export CSV/Excel.
    """
    # 1. Ambil semua data legacy
    queryset = MagneticObservation.objects.filter(
        deklinasi_readings__is_legacy=True
    ).order_by('-observation_date', '-session')
    
    # 2. Tangkap parameter filter dari URL (GET request)
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    # 3. Terapkan filter ke database jika tanggalnya diisi
    if start_date_str:
        start_date = parse_date(start_date_str)
        if start_date:
            queryset = queryset.filter(observation_date__gte=start_date)
            
    if end_date_str:
        end_date = parse_date(end_date_str)
        if end_date:
            queryset = queryset.filter(observation_date__lte=end_date)

    # 4. Fitur EXPORT TO EXCEL/CSV
    if request.GET.get('export') == 'xls':
        # Setup HTTP response agar browser mengunduh file
        response = HttpResponse(content_type='text/csv')
        # Menambahkan BOM agar karakter terbaca sempurna di Microsoft Excel
        response.write('\ufeff'.encode('utf8'))
        response['Content-Disposition'] = 'attachment; filename="Data_Absolut.csv"'
        
        # Menggunakan koma (,) sebagai pemisah standar. Jika Excel Anda berantakan, ganti koma dengan titik koma (;)
        writer = csv.writer(response, delimiter=',')
        
        # Tulis baris Header (Judul Kolom)
        writer.writerow(['Date', 'Session', 'Observer', 'Declination (D)', 'Inclination (I)', 'F (nT)', 'H (nT)', 'Z (nT)', 'X (nT)', 'Y (nT)'])
        
        # Tulis isi datanya baris demi baris
        for obs in queryset:
            writer.writerow([
                obs.observation_date,
                obs.session,
                obs.observer,
                obs.declination,
                obs.inclination,
                obs.total_intensity,
                obs.horizontal_intensity,
                obs.vertical_intensity,
                obs.north_component,
                obs.east_component
            ])
        return response

    # 5. Pagination untuk tampilan Web (20 data per halaman)
    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'observations': page_obj,
        'page_title': 'Data Absolut Backup',
        # Kirim kembali tanggal ke template agar menempel di input box
        'start_date': start_date_str, 
        'end_date': end_date_str,
    }
    return render(request, 'magnet/observation_legacy_list.html', context)

# ── LEMI-018 Monitor API ──────────────────────────────────────────────────────

import subprocess
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.conf import settings as dj_settings
from django.utils import timezone
from datetime import timedelta
from .models import LEMIStatus
import json as _json

def _send_lemi_telegram(status, computer_name):
    token   = dj_settings.TELEGRAM_BOT_TOKEN
    chat_id = dj_settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return
    if status == LEMIStatus.STATUS_NOT_RESPONDING:
        msg = (
            "🚨 <b>PERINGATAN LEMI-018</b>\n\n"
            f"⚠️ LEMI-018 <b>TIDAK MERESPONS</b>\n"
            f"Komputer: <b>{computer_name}</b>\n\n"
            "Segera restart aplikasi LEMI-018!"
        )
    else:
        msg = (
            "🚨 <b>PERINGATAN LEMI-018</b>\n\n"
            f"❌ LEMI-018 <b>TIDAK BERJALAN</b>\n"
            f"Komputer: <b>{computer_name}</b>\n\n"
            "Segera buka aplikasi LEMI-018!"
        )
    subprocess.run([
        'curl', '-s', '-X', 'POST',
        f'https://api.telegram.org/bot{token}/sendMessage',
        '-d', f'chat_id={chat_id}',
        '-d', 'parse_mode=HTML',
        '--data-urlencode', f'text={msg}',
    ])


@csrf_exempt
def lemi_status_api(request):
    if request.method == 'GET':
        try:
            latest = LEMIStatus.objects.latest()
            stale  = (timezone.now() - latest.reported_at) > timedelta(minutes=5)
            return JsonResponse({
                'status':        'monitor_offline' if stale else latest.status,
                'computer_name': latest.computer_name,
                'reported_at':   latest.reported_at.isoformat(),
                'stale':         stale,
            })
        except LEMIStatus.DoesNotExist:
            return JsonResponse({'status': 'unknown', 'stale': True})

    if request.method == 'POST':
        token    = request.headers.get('Authorization', '').removeprefix('Bearer ').strip()
        expected = getattr(dj_settings, 'LEMI_MONITOR_TOKEN', '')
        if not expected or token != expected:
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        try:
            data          = _json.loads(request.body)
            new_status    = data.get('status', '')
            computer_name = data.get('computer_name', 'LEMI-PC')
        except Exception:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        if new_status not in (LEMIStatus.STATUS_OK, LEMIStatus.STATUS_NOT_RESPONDING, LEMIStatus.STATUS_NOT_RUNNING):
            return JsonResponse({'error': 'Invalid status'}, status=400)

        # Detect transition to alert state → send Telegram once
        try:
            prev = LEMIStatus.objects.latest()
            was_ok = prev.status == LEMIStatus.STATUS_OK
        except LEMIStatus.DoesNotExist:
            was_ok = True

        LEMIStatus.objects.create(status=new_status, computer_name=computer_name)

        if new_status != LEMIStatus.STATUS_OK and was_ok:
            _send_lemi_telegram(new_status, computer_name)

        # Keep only the last 500 rows
        old_ids = LEMIStatus.objects.values_list('id', flat=True)[500:]
        if old_ids:
            LEMIStatus.objects.filter(id__in=list(old_ids)).delete()

        return JsonResponse({'ok': True, 'status': new_status})

    return JsonResponse({'error': 'Method not allowed'}, status=405)
