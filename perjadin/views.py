import calendar
from datetime import date
from django.shortcuts import render, get_object_or_404,redirect
from .models import Pegawai, PerjalananDinas, JenisPerjadin
from django.http import HttpResponseForbidden, HttpResponse
from django.db.models import Q

def index_perjadin(request):
    if not request.user.is_authenticated or request.user.username != 'jambari':
        return HttpResponseForbidden("Akses Ditolak.")
    
    today = date.today()
    # Mengambil bulan dan tahun dari URL, jika tidak ada gunakan bulan berjalan
    month = int(request.GET.get('month', today.month))
    year = int(request.GET.get('year', today.year))
    
    num_days = calendar.monthrange(year, month)[1]
    days = range(1, num_days + 1)
    
    # --- LOGIKA NAVIGASI BULAN ---
    prev_month = month - 1
    prev_year = year
    if prev_month == 0:
        prev_month = 12
        prev_year = year - 1

    next_month = month + 1
    next_year = year
    if next_month == 13:
        next_month = 1
        next_year = year + 1
    # -----------------------------

    pegawai_list = Pegawai.objects.filter(tanggal_keluar__isnull=True).order_by('urutan')
    
    rekap_data = []
    for p in pegawai_list:
        status_per_hari = []
        # Filter perjalanan yang bersinggungan dengan bulan yang dipilih
        trips_this_month = p.perjadins.filter(
            Q(tgl_mulai__month=month, tgl_mulai__year=year) | 
            Q(tgl_selesai__month=month, tgl_selesai__year=year)
        )
        
        for d in days:
            curr_date = date(year, month, d)
            is_dinas = trips_this_month.filter(tgl_mulai__lte=curr_date, tgl_selesai__gte=curr_date).exists()
            status_per_hari.append('PD' if is_dinas else '')
        
        total_uang = sum(t.total_biaya for t in trips_this_month)
        
        rekap_data.append({
            'pegawai': p,
            'status_hari': status_per_hari,
            'total_trips': trips_this_month.count(),
            'total_uang': total_uang
        })

    context = {
        'days': days,
        'rekap_data': rekap_data,
        'month_name': calendar.month_name[month],
        'current_month': month,
        'current_year': year,
        'prev_month': prev_month,
        'prev_year': prev_year,
        'next_month': next_month,
        'next_year': next_year,
        'jenis_list': JenisPerjadin.objects.all(),
        'pegawai_all': pegawai_list,
    }
    
    return render(request, 'perjadin/index.html', context)

def tambah_perjadin(request):
    if request.method == 'POST':
        p_id = request.POST.get('pegawai')
        j_id = request.POST.get('jenis')
        tujuan = request.POST.get('tujuan')
        kegiatan = request.POST.get('kegiatan')
        t_mulai = request.POST.get('tgl_mulai')
        t_selesai = request.POST.get('tgl_selesai')

        curr_m = request.POST.get('current_month')
        curr_y = request.POST.get('current_year')

        if all([p_id, j_id, tujuan, t_mulai, t_selesai]):
            # CEK DUPLIKAT: Cari apakah pegawai sudah ada perjadin di tanggal tersebut
            is_exists = PerjalananDinas.objects.filter(
                pegawai_id=p_id,
                tgl_mulai=t_mulai,
                tgl_selesai=t_selesai,
                tujuan=tujuan,
                kegiatan=kegiatan
            ).exists()

            if is_exists:
                # Jika sudah ada, jangan simpan dan beri pesan (opsional)
                return redirect('perjadin:index_perjadin')

            try:
                PerjalananDinas.objects.create(
                    pegawai_id=int(p_id),
                    jenis_id=int(j_id),
                    tujuan=tujuan,
                    kegiatan=kegiatan,
                    tgl_mulai=t_mulai,
                    tgl_selesai=t_selesai,
                )
                return redirect(f'/perjadin/?month={curr_m}&year={curr_y}')
            except Exception as e:
                return HttpResponse(f"Error: {e}")
                
    return HttpResponseForbidden()

def detail_pegawai(request, pegawai_id):
    pegawai = get_object_or_404(Pegawai, id=pegawai_id)
    trips = pegawai.perjadins.all().order_by('-tgl_mulai')
    return render(request, 'perjadin/partials/detail_modal.html', {'pegawai': pegawai, 'trips': trips})