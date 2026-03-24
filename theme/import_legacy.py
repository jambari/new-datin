import csv
import os
import re
import django
from datetime import datetime
from collections import defaultdict

# 1. AUTO-DETECT DJANGO SETTINGS DARI manage.py
settings_module = None
try:
    with open('manage.py', 'r') as f:
        content = f.read()
        # Mencari string secara otomatis di dalam manage.py
        match = re.search(r"DJANGO_SETTINGS_MODULE['\"]\s*,\s*['\"]([^'\"]+)['\"]", content)
        if match:
            settings_module = match.group(1)
            print(f"🔧 Berhasil menemukan Django Settings: {settings_module}")
except Exception as e:
    print("Gagal membaca manage.py, pastikan Anda berada di folder yang benar.")

if not settings_module:
    # Jika karena alasan tertentu tetap gagal, ubah baris ini sesuai nama folder project Anda!
    settings_module = 'namaproyek.settings' 

os.environ.setdefault('DJANGO_SETTINGS_MODULE', settings_module)
django.setup()

from magnet.models import MagneticObservation

def safe_float(val):
    try:
        if val is None or str(val).strip() == "":
            return None
        # Hapus spasi dan ganti koma menjadi titik (berjaga-jaga jika ada desimal gaya Eropa)
        clean_val = str(val).strip().replace(',', '.')
        return float(clean_val)
    except ValueError:
        return None

def import_data():
    csv_file = 'legacy_data.csv'
    instances = []
    session_tracker = defaultdict(int)

    # Menggunakan utf-8-sig untuk membuang karakter gaib (BOM) Excel
    with open(csv_file, 'r', encoding='utf-8-sig') as file:
        reader = csv.DictReader(file, delimiter=',') 
        
        for row_num, row in enumerate(reader, start=2):
            date_str = row.get('tanggal')
            
            # Lewati jika tanggal kosong
            if not date_str:
                continue
                
            # 2. LOGIKA PENANGANAN FORMAT TANGGAL GANDA (STRIP & GARIS MIRING)
            try:
                obs_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                try:
                    obs_date = datetime.strptime(date_str, '%m/%d/%Y').date()
                except ValueError:
                    try:
                        obs_date = datetime.strptime(date_str, '%d/%m/%Y').date()
                    except ValueError:
                        print(f"⚠️ Baris {row_num} dilewati: Format tanggal aneh ({date_str})")
                        continue

            # Menangani pengamatan lebih dari 1 sesi dalam sehari (Otomatis Session 1, Session 2)
            session_tracker[date_str] += 1
            session_name = f"Session {session_tracker[date_str]}"

            pengamat = row.get('pengamat')
            if not pengamat or str(pengamat).strip() == "":
                pengamat = "Unknown"

            obs = MagneticObservation(
                observation_date=obs_date,
                observer=pengamat,
                session=session_name,
                declination=safe_float(row.get('deklinasi')),
                inclination=safe_float(row.get('inklinasi')),
                total_intensity=safe_float(row.get('total')),
                horizontal_intensity=safe_float(row.get('H')),
                vertical_intensity=safe_float(row.get('Z')),
                north_component=safe_float(row.get('X')),
                east_component=safe_float(row.get('Y')),
                # Flag khusus legacy
                deklinasi_readings={'is_legacy': True},
                inklinasi_readings={'is_legacy': True}
            )
            instances.append(obs)

    # 3. BULK CREATE (Simpan massal ke Database tanpa memicu kalkulasi ulang)
    if instances:
        MagneticObservation.objects.bulk_create(instances)
        print(f"\n✅ SUKSES BESAR! Sebanyak {len(instances)} data observasi historis berhasil diimpor.")
    else:
        print("\n❌ Gagal: Tidak ada data valid yang ditemukan di CSV.")

if __name__ == '__main__':
    import_data()