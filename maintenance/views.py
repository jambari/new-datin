from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Instrument, Issue
from .forms import InstrumentForm, IssueForm
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

# ==========================
# DASHBOARD & LISTS
# ==========================

@login_required
def maintenance_dashboard(request):
    total_alat = Instrument.objects.count()
    alat_aktif = Instrument.objects.filter(status='AKTIF').count()
    alat_rusak = Instrument.objects.filter(status__in=['MATI', 'BERMASALAH']).count()
    tiket_open = Issue.objects.filter(status__in=['OPEN', 'PROG']).count()
    recent_issues = Issue.objects.filter(status__in=['OPEN', 'PROG']).order_by('-tanggal_lapor')[:5]

    context = {
        'total_alat': total_alat,
        'alat_aktif': alat_aktif,
        'alat_rusak': alat_rusak,
        'tiket_open': tiket_open,
        'recent_issues': recent_issues
    }
    return render(request, 'maintenance/dashboard.html', context)

@login_required
def instrument_list(request):
    # 1. Mulai dengan mengambil semua data
    instruments_list = Instrument.objects.all().order_by('shelter')

    # 2. Tangkap parameter filter dari URL
    jenis_filter = request.GET.get('jenis')
    status_filter = request.GET.get('status')

    # 3. Terapkan Filter jika ada
    if jenis_filter:
        instruments_list = instruments_list.filter(jenis=jenis_filter)
    
    if status_filter:
        instruments_list = instruments_list.filter(status=status_filter)

    # 4. Setup Paginator (10 data per halaman)
    paginator = Paginator(instruments_list, 10) 
    page = request.GET.get('page')
    
    try:
        instruments = paginator.page(page)
    except PageNotAnInteger:
        instruments = paginator.page(1)
    except EmptyPage:
        instruments = paginator.page(paginator.num_pages)

    # 5. Siapkan Context untuk Template
    # Kita kirim juga pilihan opsi agar dropdown dinamis
    context = {
        'instruments': instruments,
        'jenis_choices': Instrument.JENIS_CHOICES,
        'status_choices': Instrument.STATUS_ALAT_CHOICES,
        'selected_jenis': jenis_filter,   # Agar dropdown tidak reset saat pindah halaman
        'selected_status': status_filter, # Agar dropdown tidak reset saat pindah halaman
    }

    return render(request, 'maintenance/instrument_list.html', context)

@login_required
def issue_list(request):
    # Ambil semua data tiket urut dari yang terbaru
    issue_data = Issue.objects.all().order_by('-tanggal_lapor')
    
    # Setup Paginator: 10 tiket per halaman
    paginator = Paginator(issue_data, 10) 

    page = request.GET.get('page')
    try:
        issues = paginator.page(page)
    except PageNotAnInteger:
        # Jika page bukan angka, kembali ke hal 1
        issues = paginator.page(1)
    except EmptyPage:
        # Jika page kelebihan, ambil hal terakhir
        issues = paginator.page(paginator.num_pages)

    return render(request, 'maintenance/issue_list.html', {'issues': issues})

# ==========================
# CRUD INSTRUMENT (ALAT)
# ==========================

@login_required
def instrument_create(request):
    if request.method == 'POST':
        form = InstrumentForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('maintenance:instrument_list')
    else:
        form = InstrumentForm()
    
    context = {'form': form, 'title': 'Tambah Alat Baru'}
    return render(request, 'maintenance/form_generic.html', context)

@login_required
def instrument_update(request, pk):
    # Baris ini yang sebelumnya error karena get_object_or_404 belum di-import
    instrument = get_object_or_404(Instrument, pk=pk)
    
    if request.method == 'POST':
        form = InstrumentForm(request.POST, instance=instrument)
        if form.is_valid():
            form.save()
            return redirect('maintenance:instrument_list')
    else:
        form = InstrumentForm(instance=instrument)

    context = {'form': form, 'title': f'Edit Alat: {instrument.nama_alat}'}
    return render(request, 'maintenance/form_generic.html', context)

@login_required
def instrument_delete(request, pk):
    instrument = get_object_or_404(Instrument, pk=pk)
    if request.method == 'POST':
        instrument.delete()
        return redirect('maintenance:instrument_list')
    
    context = {'object': instrument, 'type_name': 'Alat'}
    return render(request, 'maintenance/confirm_delete.html', context)


# ==========================
# CRUD ISSUE (TIKET)
# ==========================

@login_required
def issue_create(request):
    if request.method == 'POST':
        form = IssueForm(request.POST)
        if form.is_valid():
            issue = form.save(commit=False)
            if not issue.pic:
                issue.pic = request.user
            issue.save()
            return redirect('maintenance:issue_list')
    else:
        form = IssueForm()
    
    context = {'form': form, 'title': 'Buat Tiket Laporan Baru'}
    return render(request, 'maintenance/form_generic.html', context)

@login_required
def issue_update(request, pk):
    issue = get_object_or_404(Issue, pk=pk)
    if request.method == 'POST':
        form = IssueForm(request.POST, instance=issue)
        if form.is_valid():
            form.save()
            return redirect('maintenance:issue_list')
    else:
        form = IssueForm(instance=issue)

    context = {'form': form, 'title': f'Update Tiket: {issue.judul}'}
    return render(request, 'maintenance/form_generic.html', context)

@login_required
def issue_delete(request, pk):
    issue = get_object_or_404(Issue, pk=pk)
    if request.method == 'POST':
        issue.delete()
        return redirect('maintenance:issue_list')
    
    context = {'object': issue, 'type_name': 'Tiket Laporan'}
    return render(request, 'maintenance/confirm_delete.html', context)