# hujan/views.py

from django.shortcuts import render, redirect, get_object_or_404 # Add redirect and get_object_or_404
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from .models import Hujan
from django.db.models import Max, Count, Q, Sum
from datetime import datetime
import json
from .forms import HujanForm, KATEGORI_CHOICES
from jadwal.models import Pegawai


def daftar_hujan(request):
    qs = Hujan.objects.all().order_by('-tanggal')

    # --- Filters (all optional, combined with AND) ---
    f_start = request.GET.get('start', '').strip()
    f_end = request.GET.get('end', '').strip()
    f_kategori = request.GET.get('kategori', '').strip()
    f_petugas = request.GET.get('petugas', '').strip()
    f_q = request.GET.get('q', '').strip()

    if f_start:
        qs = qs.filter(tanggal__gte=f_start)
    if f_end:
        qs = qs.filter(tanggal__lte=f_end)
    if f_kategori:
        qs = qs.filter(kategori=f_kategori)
    if f_petugas:
        qs = qs.filter(petugas=f_petugas)
    if f_q:
        qs = qs.filter(keterangan__icontains=f_q)

    paginator = Paginator(qs, 10)
    page = request.GET.get('page')
    try:
        hujan_records = paginator.page(page)
    except PageNotAnInteger:
        hujan_records = paginator.page(1)
    except EmptyPage:
        hujan_records = paginator.page(paginator.num_pages)

    # Preserve active filters across pagination links (drop the page param).
    params = request.GET.copy()
    params.pop('page', None)
    querystring = params.urlencode()

    petugas_list = (Pegawai.objects.filter(tanggal_keluar__isnull=True)
                    .order_by('nama').values_list('nama', flat=True))

    context = {
        'hujan_records': hujan_records,
        'kategori_choices': KATEGORI_CHOICES,
        'petugas_list': petugas_list,
        'f_start': f_start,
        'f_end': f_end,
        'f_kategori': f_kategori,
        'f_petugas': f_petugas,
        'f_q': f_q,
        'querystring': querystring,
        'has_filters': any([f_start, f_end, f_kategori, f_petugas, f_q]),
    }
    return render(request, 'hujan/daftar_hujan.html', context)

def query_laporan_hujan(request):
    start_date = request.GET.get('start')
    end_date = request.GET.get('end')
    
    hujan_records = []
    stats = {}
    
    # Data untuk Chart (List kosong default)
    chart_dates = []
    chart_obs = []
    pie_labels = []
    pie_data = []

    if start_date and end_date:
        # 1. Filter Data (Urutkan tanggal asc untuk grafik)
        hujan_records = Hujan.objects.filter(
            tanggal__range=[start_date, end_date]
        ).order_by('tanggal')
        total_hujan = hujan_records.aggregate(Sum('obs'))['obs__sum'] or 0

        if hujan_records.exists():
            # --- LOGIKA NARASI (Hanya Obs) ---
            # Cari Max Obs
            max_hujan = hujan_records.aggregate(Max('obs'))
            max_val = max_hujan['obs__max']
            
            # Cari object detail dari nilai max tersebut
            max_obj = hujan_records.filter(obs=max_val).first()
            
            # Hitung Hari Hujan (Obs > 0)
            total_hari_hujan = hujan_records.filter(obs__gt=0).count()
            
            # Nama Bulan & Tahun untuk Narasi
            dt_obj = datetime.strptime(start_date, '%Y-%m-%d')
            bulan_tahun = dt_obj.strftime('%B %Y') # Contoh: November 2025

            stats = {
                'bulan_str': bulan_tahun,
                'total_hari_hujan': total_hari_hujan,
                'max_val': max_val,
                'max_date': max_obj.tanggal if max_obj else None,
                'max_kategori': max_obj.kategori if max_obj else '-',
                'total_hujan': total_hujan,
            }

            # --- PERSIAPAN DATA BAR CHART (OBS) ---
            for h in hujan_records:
                # Format tanggal jadi angka tanggal saja (1, 2, 3...) agar sumbu X rapi
                chart_dates.append(h.tanggal.day) 
                chart_obs.append(h.obs)

            # --- PERSIAPAN DATA PIE CHART (GROUP BY KATEGORI) ---
            # Menghitung jumlah kemunculan setiap kategori
            kategori_stats = hujan_records.values('kategori').annotate(total=Count('kategori')).order_by('-total')
            
            for item in kategori_stats:
                pie_labels.append(item['kategori']) # e.g., "Sedang", "Nihil"
                pie_data.append(item['total'])      # e.g., 5, 10

    context = {
        'hujan_records': hujan_records,
        'start_date': start_date,
        'end_date': end_date,
        'stats': stats,
        # Dump data ke JSON string untuk JS
        'chart_dates': json.dumps(chart_dates),
        'chart_obs': json.dumps(chart_obs),
        'pie_labels': json.dumps(pie_labels),
        'pie_data': json.dumps(pie_data),
    }

    return render(request, 'hujan/laporan_query.html', context)

def tambah_hujan(request):
    if request.method == 'POST':
        form = HujanForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('daftar_hujan')
    else:
        form = HujanForm()

    context = {
        'form': form,
        'title': 'Tambah Data Hujan',
        'submit_label': 'Simpan',
    }
    return render(request, 'hujan/form_hujan.html', context)

def edit_hujan(request, id):
    # Get the specific record or return 404 if not found
    hujan_instance = get_object_or_404(Hujan, id=id)

    if request.method == 'POST':
        form = HujanForm(request.POST, instance=hujan_instance)
        if form.is_valid():
            form.save()
            return redirect('daftar_hujan') # Redirect back to list after saving
    else:
        # Pre-fill the form with existing data
        form = HujanForm(instance=hujan_instance)

    context = {
        'form': form,
        'title': 'Edit Data Hujan',
        'submit_label': 'Simpan Perubahan',
    }
    return render(request, 'hujan/form_hujan.html', context)