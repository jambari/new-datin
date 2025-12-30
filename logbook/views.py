from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from .models import Logbook
from .forms import LogbookForm
from .utils import send_telegram_log
import zoneinfo # Untuk pengaturan zona waktu Jayapura
from jadwal.models import JadwalHVSampler # Import model Jadwal HV Sampler

ALLOWED_IPS = ['36.91.166.189', '36.91.166.186', '127.0.0.1']

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def index(request):
    user_ip = get_client_ip(request)
    is_authorized = user_ip in ALLOWED_IPS
    
    # --- LOGIKA WAKTU JAYAPURA (WIT) ---
    tz_jayapura = zoneinfo.ZoneInfo("Asia/Jayapura")
    now_jayapura = timezone.now().astimezone(tz_jayapura)
    today_jayapura = now_jayapura.date()
    
    # 1. Cek Jadwal Air Hujan (Setiap Senin)
    # weekday() returns 0 for Monday
    is_hari_senin = today_jayapura.weekday() == 0
    
    # 2. Cek Jadwal HV Sampler di Database untuk hari ini
    hv_today = JadwalHVSampler.objects.filter(tanggal=today_jayapura).first()
    
    # --- LOGIC PENYIMPANAN DATA (POST) ---
    if request.method == 'POST':
        if not is_authorized:
            messages.error(request, f"Akses Ditolak. IP Anda ({user_ip}) tidak terdaftar.")
            return redirect('logbook:logbook_list')
            
        form = LogbookForm(request.POST)
        if form.is_valid():
            log_entry = form.save(commit=False)
            if request.user.is_authenticated:
                log_entry.petugas = request.user
            
            # Tetap simpan tanggal berdasarkan input/auto hari ini
            log_entry.save()
            
            try:
                send_telegram_log(log_entry)
            except Exception as e:
                print(f"Telegram Error: {e}")

            messages.success(request, "Log berhasil disimpan.")
            return redirect('logbook:logbook_list')
    else:
        form = LogbookForm()

    # --- LOGIC FILTER & PAGINATION (GET) ---
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    logs_list = Logbook.objects.all().order_by('-waktu_dibuat')

    if start_date and end_date:
        logs_list = logs_list.filter(tanggal__range=[start_date, end_date])
        filter_info = f"Periode: {start_date} s.d {end_date}"
    else:
        # Tampilkan data berdasarkan tanggal Jayapura hari ini
        logs_list = logs_list.filter(tanggal=today_jayapura)
        filter_info = f"Hari Ini ({today_jayapura.strftime('%d %b %Y')})"
        start_date = str(today_jayapura)
        end_date = str(today_jayapura)

    page = request.GET.get('page', 1)
    paginator = Paginator(logs_list, 10) 
    
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    context = {
        'form': form,
        'is_authorized': is_authorized,
        'user_ip': user_ip,
        'page_obj': page_obj,
        'filter_info': filter_info,
        'start_date': start_date,
        'end_date': end_date,
        # Variabel Notifikasi Jadwal
        'is_hari_senin': is_hari_senin,
        'hv_today': hv_today,
    }
    return render(request, 'logbook/index.html', context)

def print_log_detail(request, log_id):
    log = get_object_or_404(Logbook, pk=log_id)
    context = {
        'log': log,
        'user': request.user
    }
    return render(request, 'logbook/print_detail.html', context)

def edit_log(request, log_id):
    user_ip = get_client_ip(request)
    if user_ip not in ALLOWED_IPS:
        messages.error(request, f"Akses Ditolak. IP Anda ({user_ip}) tidak terdaftar.")
        return redirect('logbook:logbook_list')

    log_entry = get_object_or_404(Logbook, pk=log_id)

    if request.method == 'POST':
        form = LogbookForm(request.POST, instance=log_entry)
        if form.is_valid():
            saved_log = form.save()
            try:
                send_telegram_log(saved_log, is_update=True)
            except Exception as e:
                print(f"Telegram Error: {e}")
                
            messages.success(request, "Log berhasil diperbarui.")
            return redirect('logbook:logbook_list')
    else:
        form = LogbookForm(instance=log_entry)

    context = {
        'form': form,
        'log_entry': log_entry,
        'is_edit_mode': True 
    }
    return render(request, 'logbook/edit_log.html', context)