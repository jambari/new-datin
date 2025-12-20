from django.db.models import Q
import calendar
from datetime import date, datetime, timedelta
from django.shortcuts import render, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum
from .models import Pegawai, JadwalHarian, PolaDinas, RiwayatJadwal
import random
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
import json
from django.views.decorators.csrf import csrf_exempt

@staff_member_required
def tabel_jadwal(request):
    # Ambil parameter bulan dan tahun dari URL, atau default ke bulan ini
    today = date.today()
    try:
        selected_month = int(request.GET.get('month', today.month))
        selected_year = int(request.GET.get('year', today.year))
    except ValueError:
        selected_month = today.month
        selected_year = today.year

    # Ganti dengan Dictionary Bahasa Indonesia:
    NAMA_BULAN = {
        1: 'JANUARI', 2: 'FEBRUARI', 3: 'MARET', 4: 'APRIL',
        5: 'MEI', 6: 'JUNI', 7: 'JULI', 8: 'AGUSTUS',
        9: 'SEPTEMBER', 10: 'OKTOBER', 11: 'NOVEMBER', 12: 'DESEMBER'
    }

    month_name = NAMA_BULAN[selected_month]
    _, num_days = calendar.monthrange(selected_year, selected_month)
    list_tanggal = range(1, num_days + 1)

    start_of_month = date(selected_year, selected_month, 1)
    # Ambil semua pegawai
    pegawai_list = Pegawai.objects.filter(
        Q(tanggal_keluar__isnull=True) | Q(tanggal_keluar__gte=start_of_month)
    )

    # Struktur Data untuk Tabel
    laporan = []
    
    for p in pegawai_list:
        row = {
            'pegawai': p,
            'hari': {}, # Dictionary tanggal: data
            'total_jam': 0,
            'uang_makan': 0
        }

        # Ambil jadwal pegawai ini dalam bulan terpilih
        jadwal_bulan = JadwalHarian.objects.filter(
            pegawai=p,
            tanggal__year=selected_year,
            tanggal__month=selected_month
        ).select_related('pola')

        # Map jadwal ke tanggal
        jadwal_map = {j.tanggal.day: j for j in jadwal_bulan}

        for tgl in list_tanggal:
            current_date = date(selected_year, selected_month, tgl)
            is_weekend = current_date.weekday() >= 5 # 5=Sat, 6=Sun
            
            data_sel = jadwal_map.get(tgl)
            cell_data = {'kode': '', 'warna': '#ffffff', 'css_class': ''}

            if data_sel:
                # Prioritas 1: Keterangan Lain (DL, Cuti, TB)
                if data_sel.keterangan_lain:
                    if data_sel.keterangan_lain == 'TB':
                        cell_data['kode'] = 'TB'
                        cell_data['warna'] = '#cccccc' # Abu-abu
                    elif data_sel.keterangan_lain == 'DL':
                        cell_data['kode'] = 'DL'
                        cell_data['warna'] = '#ffff00' # Kuning (misal)
                    elif data_sel.keterangan_lain == 'CUTI':
                        cell_data['kode'] = 'C'
                        cell_data['warna'] = '#ffcccc'
                    # Hitung jam untuk DL? Tergantung aturan.
                    # Asumsi DL dihitung standar 7.5 jam x hari kerja
                    if data_sel.keterangan_lain == 'DL':
                        row['total_jam'] += 7.5
                
                # Prioritas 2: Pola Dinas
                elif data_sel.pola:
                    cell_data['kode'] = data_sel.pola.kode
                    cell_data['warna'] = data_sel.pola.warna
                    row['total_jam'] += data_sel.pola.durasi
            
            else:
                # Jika kosong
                if p.is_reguler and is_weekend:
                    cell_data['kode'] = 'L' # Libur weekend reguler
                    cell_data['warna'] = '#e0e0e0'
                else:
                    cell_data['kode'] = ''
            
            row['hari'][tgl] = cell_data

        # Hitung Uang Makan = Total Jam / 7.5
        # Menggunakan floor division (pembulatan ke bawah) atau float
        if row['total_jam'] > 0:
            row['uang_makan'] = int(row['total_jam'] / 7.5)
        
        laporan.append(row)

    history_list = RiwayatJadwal.objects.filter(
        bulan=selected_month, 
        tahun=selected_year
    )[:5]

    context = {
        'month': selected_month,
        'year': selected_year,
        'month_name': month_name,
        'days_range': list_tanggal,
        'laporan': laporan,
        'pegawai_all': pegawai_list,
        'today_year': today.year,
        'next_month': selected_month + 1 if selected_month < 12 else 1,
        'next_year': selected_year if selected_month < 12 else selected_year + 1,
        'prev_month': selected_month - 1 if selected_month > 1 else 12,
        'prev_year': selected_year if selected_month > 1 else selected_year - 1,
        'history_list': history_list,
    }

    return render(request, 'jadwal/tabel_dinas.html', context)

@require_POST
@staff_member_required
def generate_auto_schedule(request):
    try:
        month = int(request.POST.get('month'))
        year = int(request.POST.get('year'))
        pola_type = request.POST.get('pola_type')
        start_day = int(request.POST.get('start_day', 1))
        
        exceptions_json = request.POST.get('exceptions_data', '[]')
        exceptions_list = json.loads(exceptions_json)

        MIN_JAM_KERJA = 138.0
        _, num_days = calendar.monthrange(year, month)
        days_list = list(range(start_day, num_days + 1))
        
        # Tentukan Tanggal Mulai Generate
        start_date_obj = date(year, month, start_day)
        create_backup(month, year, request.user, note=f"Backup sebelum Generate Pola {request.POST.get('pola_type')}")

        with transaction.atomic():
            # 1. BERSIHKAN JADWAL (Hanya dari tanggal start_day ke depan)
            JadwalHarian.objects.filter(
                tanggal__year=year, 
                tanggal__month=month, 
                tanggal__day__gte=start_day
            ).delete()

            # ===================================================
            # TAHAP 1: TERAPKAN EXCEPTIONS (LN/CB/TB/ST/C)
            # ===================================================
            for exc in exceptions_list:
                try:
                    p_id = int(exc['id'])
                    kode = exc['kode']
                    t_start = int(exc['start'])
                    t_end = int(exc['end'])
                    
                    pegawai = Pegawai.objects.get(id=p_id)
                    pola_exc = PolaDinas.objects.get(kode=kode)
                    
                    for d in range(t_start, t_end + 1):
                        if d >= start_day and d <= num_days:
                            JadwalHarian.objects.update_or_create(
                                pegawai=pegawai,
                                tanggal=date(year, month, d),
                                defaults={'pola': pola_exc}
                            )
                except: continue

            # ===================================================
            # TAHAP 2: ISI PEGAWAI REGULER (R)
            # ===================================================
            try:
                pola_reguler = PolaDinas.objects.get(kode='R')
                pegawai_reguler = Pegawai.objects.filter(is_reguler=True)
                for peg in pegawai_reguler:
                    for d in days_list:
                        tgl = date(year, month, d)
                        # Senin-Jumat & Bukan Libur Nasional (LN/CB)
                        if tgl.weekday() < 5: 
                            if not JadwalHarian.objects.filter(pegawai=peg, tanggal=tgl).exists():
                                JadwalHarian.objects.create(pegawai=peg, tanggal=tgl, pola=pola_reguler)
            except PolaDinas.DoesNotExist: pass

            # ===================================================
            # TAHAP 3: ISI PEGAWAI SHIFT (SMART LOGIC)
            # ===================================================
            pegawai_shift = list(Pegawai.objects.filter(is_reguler=False))
            if not pegawai_shift:
                 return JsonResponse({'status': 'error', 'message': 'Tidak ada pegawai shift.'})

            # A. SETUP TRACKER JAM KERJA (Saldo Awal)
            # Hitung jam kerja yang SUDAH didapat dari tgl 1 s.d start_day-1
            jam_tracker = {p.id: 0.0 for p in pegawai_shift}
            
            existing = JadwalHarian.objects.filter(
                tanggal__year=year, tanggal__month=month,
                tanggal__day__lt=start_day, pegawai__is_reguler=False
            ).select_related('pola')
            
            for j in existing:
                if j.pola and j.pola.durasi: jam_tracker[j.pegawai.id] += j.pola.durasi

            # B. SETUP POLA
            pola_main = PolaDinas.objects.get(kode='PSM') if pola_type == 'PSM' else PolaDinas.objects.get(kode='PS')
            pola_sec = PolaDinas.objects.get(kode='MT') if pola_type == 'PS-MT' else None

            # C. LOOPING HARI (ALGORITMA UTAMA)
            for day in days_list:
                current_date = date(year, month, day)
                yesterday = current_date - timedelta(days=1)
                
                # C.1: CEK SIAPA YANG DINAS KEMARIN (Termasuk Lintas Bulan)
                # Query DB untuk melihat jadwal kemarin
                jadwal_kemarin = JadwalHarian.objects.filter(tanggal=yesterday).values_list('pegawai_id', flat=True)
                # Ubah ke set agar pencarian cepat
                id_petugas_kemarin = set(jadwal_kemarin) 

                # C.2: CARI KANDIDAT YANG ELIGIBLE (MEMENUHI SYARAT)
                candidates = []
                for p in pegawai_shift:
                    # Syarat 1: Tidak sedang Cuti/TB/ST hari ini (Cek Exception Tahap 1)
                    is_busy_today = JadwalHarian.objects.filter(pegawai=p, tanggal=current_date).exists()
                    
                    # Syarat 2: TIDAK DINAS KEMARIN (Aturan Istirahat)
                    worked_yesterday = p.id in id_petugas_kemarin
                    
                    if not is_busy_today and not worked_yesterday:
                        # Masukkan ke daftar kandidat beserta jam kerjanya saat ini
                        candidates.append({
                            'pegawai': p,
                            'current_hours': jam_tracker[p.id]
                        })

                # C.3: SORTIR KANDIDAT BERDASARKAN JAM KERJA TERENDAH
                # Agar pembagian jam rata, prioritaskan yang jamnya paling sedikit
                candidates.sort(key=lambda x: x['current_hours']) # Ascending sort

                if not candidates:
                    # DARURAT: Tidak ada yang bisa dinas (Semua kerja kemarin / Cuti)
                    # Solusi: Terpaksa ambil yang kerja kemarin (Double Shift) atau biarkan kosong?
                    # Kita biarkan kosong agar admin sadar ada konflik, atau ambil random.
                    continue 

                # C.4: ASSIGN JADWAL
                # Petugas 1
                p1_data = candidates[0]
                p1 = p1_data['pegawai']
                JadwalHarian.objects.create(pegawai=p1, tanggal=current_date, pola=pola_main)
                jam_tracker[p1.id] += pola_main.durasi
                
                # Petugas 2 (Jika PS-MT)
                if pola_type == 'PS-MT' and len(candidates) > 1:
                    p2_data = candidates[1]
                    p2 = p2_data['pegawai']
                    JadwalHarian.objects.create(pegawai=p2, tanggal=current_date, pola=pola_sec)
                    jam_tracker[p2.id] += pola_sec.durasi

            # ===================================================
            # TAHAP 4: BOOSTER (HANYA MENGISI SLOT LIBUR)
            # ===================================================
            # Isi kekurangan jam dengan syarat ketat:
            # 1. Tidak boleh tabrakan jadwal sendiri
            # 2. Tidak boleh tabrakan dengan jadwal kemarin (istirahat)
            # 3. Tidak boleh tabrakan dengan jadwal besok (biar besok fit)
            
            pola_booster = pola_main
            for p in pegawai_shift:
                safety = 0
                while jam_tracker[p.id] < MIN_JAM_KERJA and safety < 100:
                    random.shuffle(days_list)
                    filled = False
                    for d_chk in days_list:
                        t_chk = date(year, month, d_chk)
                        y_chk = t_chk - timedelta(days=1)
                        tm_chk = t_chk + timedelta(days=1)

                        # Cek Ketersediaan Penuh
                        busy_today = JadwalHarian.objects.filter(pegawai=p, tanggal=t_chk).exists()
                        busy_yesterday = JadwalHarian.objects.filter(pegawai=p, tanggal=y_chk).exists()
                        busy_tomorrow = JadwalHarian.objects.filter(pegawai=p, tanggal=tm_chk).exists()

                        # Syarat Booster: Hari ini kosong, Kemarin Kosong, Besok Kosong (Ideal)
                        # Atau minimal Kemarin Kosong.
                        if not busy_today and not busy_yesterday: 
                             # Cek juga apakah slot di hari itu sudah penuh? (Max 2 atau 3 org)
                             # Optional: Jika ingin strict max 2 orang per hari, query count dulu.
                             
                             JadwalHarian.objects.create(pegawai=p, tanggal=t_chk, pola=pola_booster)
                             jam_tracker[p.id] += pola_booster.durasi
                             filled = True
                             break
                    
                    if not filled: break
                    safety += 1

        return JsonResponse({'status': 'success', 'message': 'Jadwal sukses! Aturan libur setelah dinas & Lintas bulan telah diterapkan.'})

    except Exception as e:
        import traceback
        return JsonResponse({'status': 'error', 'message': str(e)})
    
@csrf_exempt
@staff_member_required
def update_jadwal_api(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        pegawai_id = data.get('pegawai_id')
        tanggal_str = data.get('tanggal') 
        kode_pola = data.get('kode_pola') 

        try:
            pegawai = Pegawai.objects.get(id=pegawai_id)
            tgl = datetime.strptime(tanggal_str, "%Y-%m-%d").date()
            
            # 1. PROSES SIMPAN / HAPUS JADWAL
            pola_obj = None
            if not kode_pola:
                # Jika kode kosong, hapus jadwal
                JadwalHarian.objects.filter(pegawai=pegawai, tanggal=tgl).delete()
                status_res = 'deleted'
                warna_res = 'transparent'
                kode_res = ''
            else:
                # Cari Pola
                pola_obj = PolaDinas.objects.filter(kode=kode_pola).first()
                if not pola_obj:
                     return JsonResponse({'status': 'error', 'message': 'Pola tidak valid'})

                # Update atau Create
                JadwalHarian.objects.update_or_create(
                    pegawai=pegawai,
                    tanggal=tgl,
                    defaults={'pola': pola_obj}
                )
                status_res = 'saved'
                warna_res = pola_obj.warna
                kode_res = pola_obj.kode

            # 2. HITUNG ULANG TOTAL JAM & UM (Real-time Calculation)
            # Ambil bulan dan tahun dari tanggal yang diedit
            month = tgl.month
            year = tgl.year
            
            # Hitung total durasi bulan ini untuk pegawai ini saja
            jadwal_sebulan = JadwalHarian.objects.filter(
                pegawai=pegawai,
                tanggal__month=month,
                tanggal__year=year
            ).select_related('pola')

            total_jam_baru = 0
            for j in jadwal_sebulan:
                if j.pola and j.pola.durasi:
                    total_jam_baru += j.pola.durasi
            
            # Hitung Uang Makan (UM)
            uang_makan_baru = int(total_jam_baru / 7.5)

            # 3. KIRIM BALIK KE BROWSER
            return JsonResponse({
                'status': status_res,
                'pola': kode_res,
                'warna': warna_res,
                # Data baru untuk update tabel:
                'new_total_jam': int(total_jam_baru), # Kirim angka bulat
                'new_uang_makan': uang_makan_baru
            })

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
            
    return JsonResponse({'status': 'error', 'message': 'Invalid request'})

def create_backup(month, year, user, note="Backup Otomatis"):
    # 1. Ambil semua jadwal bulan itu
    jadwal_objs = JadwalHarian.objects.filter(
        tanggal__year=year, 
        tanggal__month=month
    ).select_related('pola', 'pegawai')
    
    # 2. Konversi ke List of Dictionaries (JSON Friendly)
    data_list = []
    for j in jadwal_objs:
        if j.pola:
            data_list.append({
                'pegawai_id': j.pegawai.id,
                'day': j.tanggal.day,
                'pola_kode': j.pola.kode
            })
            
    # 3. Simpan jika ada datanya
    if data_list:
        RiwayatJadwal.objects.create(
            bulan=month,
            tahun=year,
            user=user,
            keterangan=note,
            data_snapshot=data_list
        )

@staff_member_required
def restore_jadwal(request, backup_id):
    backup = get_object_or_404(RiwayatJadwal, id=backup_id)
    month = backup.bulan
    year = backup.tahun
    
    with transaction.atomic():
        # 1. Hapus jadwal saat ini (bersihkan)
        JadwalHarian.objects.filter(tanggal__year=year, tanggal__month=month).delete()
        
        # 2. Loop data JSON dan create ulang
        for item in backup.data_snapshot:
            try:
                pegawai = Pegawai.objects.get(id=item['pegawai_id'])
                pola = PolaDinas.objects.get(kode=item['pola_kode'])
                tgl = date(year, month, item['day'])
                
                JadwalHarian.objects.create(
                    pegawai=pegawai,
                    tanggal=tgl,
                    pola=pola
                )
            except Exception:
                continue # Skip jika pegawai/pola sdh dihapus master datanya
                
    return redirect(f'/jadwal/?month={month}&year={year}')