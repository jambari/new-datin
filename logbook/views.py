from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from .models import Logbook
from .forms import LogbookForm
from .utils import send_telegram_log
import zoneinfo
from jadwal.models import JadwalHVSampler

ALLOWED_IPS = ['36.91.166.189', '36.91.166.186', '127.0.0.1']

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')

def index(request):
    user_ip = get_client_ip(request)
    is_authorized = user_ip in ALLOWED_IPS
    tz_jayapura = zoneinfo.ZoneInfo("Asia/Jayapura")
    now_jayapura = timezone.now().astimezone(tz_jayapura)
    today_jayapura = now_jayapura.date()
    day_of_week = today_jayapura.weekday() # 0=Senin, 1=Selasa...

    # --- LOGIKA NOTIFIKASI JADWAL RUTIN ---
    notif_rutin = []
    if day_of_week == 0: 
        notif_rutin.append("Pengambilan Sampel Air Hujan pukul 09:00 WIT")
    if day_of_week in [2, 4]: notif_rutin.append("Jadwal Pengamatan Absolut pukul 09:00 WIT") # Rabu & Jumat
    if day_of_week == 4: notif_rutin.append("Jadwal Pembuatan Infografis") # Jumat
    if day_of_week in [0, 3]: notif_rutin.append("Jadwal Penyusunan Laporan Prekursor pukul 09:00 WIT") # Senin & Kamis

    # HV Sampler Logic
    hv_today = JadwalHVSampler.objects.filter(tanggal=today_jayapura).first()
    hv_yesterday = JadwalHVSampler.objects.filter(tanggal=today_jayapura - timezone.timedelta(days=1)).first()
    show_hv_fields = True if (hv_today or hv_yesterday) else False
    
    if request.method == 'POST':
        if not is_authorized:
            messages.error(request, f"Akses Ditolak. IP: {user_ip}")
            return redirect('logbook:logbook_list')
        form = LogbookForm(request.POST)
        if form.is_valid():
            log_entry = form.save(commit=False)
            if request.user.is_authenticated: log_entry.petugas = request.user
            log_entry.tanggal = today_jayapura 
            log_entry.save()
            form.save_m2m() #
            try: send_telegram_log(log_entry)
            except Exception as e: print(f"Telegram Error: {e}")
            messages.success(request, "Log berhasil disimpan.")
            return redirect('logbook:logbook_list')
    else:
        form = LogbookForm()

    # Filter & Pagination
    start_date = request.GET.get('start_date', str(today_jayapura))
    end_date = request.GET.get('end_date', str(today_jayapura))
    logs_list = Logbook.objects.all().order_by('-waktu_dibuat')
    if start_date and end_date: logs_list = logs_list.filter(tanggal__range=[start_date, end_date])
    
    paginator = Paginator(logs_list, 10)
    page = request.GET.get('page', 1)
    try: page_obj = paginator.page(page)
    except: page_obj = paginator.page(1)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(request, 'logbook/_log_table_partial.html', {'page_obj': page_obj})

    context = {
        'form': form, 'page_obj': page_obj, 'today_str': str(today_jayapura),
        'start_date': start_date, 'end_date': end_date, 'notif_rutin': notif_rutin,
        'hv_today': hv_today, 'show_hv_fields': show_hv_fields, 'is_authorized': is_authorized,
    }
    return render(request, 'logbook/index.html', context)

def edit_log(request, log_id):
    log_entry = get_object_or_404(Logbook, pk=log_id)
    if request.method == 'POST':
        form = LogbookForm(request.POST, instance=log_entry)
        if form.is_valid():
            saved_log = form.save(commit=False)
            saved_log.save()
            form.save_m2m() #
            try: send_telegram_log(saved_log, is_update=True)
            except Exception as e: print(f"Telegram Error: {e}")
            messages.success(request, "Log diperbarui.")
            return redirect('logbook:logbook_list')
    else:
        form = LogbookForm(instance=log_entry)
    
    show_hv_fields = JadwalHVSampler.objects.filter(tanggal__range=[log_entry.tanggal - timezone.timedelta(days=1), log_entry.tanggal]).exists()
    return render(request, 'logbook/edit_log.html', {'form': form, 'log_entry': log_entry, 'is_edit_mode': True, 'show_hv_fields': show_hv_fields})

def print_log_detail(request, log_id):
    return render(request, 'logbook/print_detail.html', {'log': get_object_or_404(Logbook, pk=log_id)})