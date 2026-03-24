import csv
import os
import django
from datetime import datetime
from collections import defaultdict

# 1. SETUP DJANGO
# Menghubungkan script Python ke sistem database Django Anda
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'datin_project.settings')
django.setup()

from magnet.models import MagneticObservation

def safe_float(val):
    """Fungsi aman untuk mengubah teks dari Excel menjadi angka desimal."""
    try:
        if val is None or str(val).strip() == "":
            return None
        # Bersihkan spasi dan ganti koma menjadi titik (jika ada format angka Eropa)
        clean_val = str(val).strip().replace(',', '.')
        return float(clean_val)
    except ValueError:
        return None

def import_data():
    csv_file = 'data_legacy.csv'
    instances = []
    session_tracker = defaultdict(int)

    # Cek apakah file benar-benar ada
    if not os.path.exists(csv_file):
        print(f"❌ File '{csv_file}' tidak ditemukan di folder ini!")
        return

    # Menggunakan utf-8-sig untuk membersihkan karakter aneh (BOM) bawaan Excel
    with open(csv_file, 'r', encoding='utf-8-sig') as file:
        
        # INI KUNCI UTAMANYA: Memaksa Python membaca menggunakan KOMA (',')
        reader = csv.DictReader(file, delimiter=',') 
        
        # Cetak header untuk memastikan kolom terpisah dengan benar
        print(f"Membaca kolom: {reader.fieldnames}\n")
        print("Memproses data, mohon tunggu...")

        for row_num, row in enumerate(reader, start=2):
            date_str = row.get('tanggal')
            
            # Jika kolom tanggal tidak ditemukan atau kosong, lewati baris ini
            if not date_str:
                continue
                
            # 2. LOGIKA PENANGANAN TANGGAL GANDA
            # Excel sering mengubah format tanggal diam-diam. Kita atasi dengan ini:
            try:
                # Coba baca format 2023-11-08 (Strip)
                obs_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                try:
                    # Coba baca format 11/8/2023 (Garis Miring ala US)
                    obs_date = datetime.strptime(date_str, '%m/%d/%Y').date()
                except ValueError:
                    try:
                        # Coba baca format 8/11/2023 (Garis Miring ala Indonesia/Eropa)
                        obs_date = datetime.strptime(date_str, '%d/%m/%Y').date()
                    except ValueError:
                        print(f"⚠️ Baris {row_num} dilewati: Format tanggal tidak dikenali -> {date_str}")
                        continue

            # Menangani jika ada 2 pengamatan di hari yang sama -> Jadikan Session 1, Session 2, dst.
            session_tracker[date_str] += 1
            session_name = f"Session {session_tracker[date_str]}"

            pengamat = row.get('pengamat')
            if not pengamat or str(pengamat).strip() == "":
                pengamat = "Unknown"

            # 3. MEMBUAT OBJEK OBSERVASI
            obs = MagneticObservation(
                observation_date=obs_date,
                observer=pengamat,
                session=session_name,
                
                # Mengambil nilai final (D, I, F, H, Z, X, Y)
                declination=safe_float(row.get('deklinasi')),
                inclination=safe_float(row.get('inklinasi')),
                total_intensity=safe_float(row.get('total')),
                horizontal_intensity=safe_float(row.get('H')),
                vertical_intensity=safe_float(row.get('Z')),
                north_component=safe_float(row.get('X')),
                east_component=safe_float(row.get('Y')),
                
                # Flag khusus agar aplikasi tahu ini data historis (Legacy)
                deklinasi_readings={'is_legacy': True},
                inklinasi_readings={'is_legacy': True}
            )
            instances.append(obs)

    # 4. PROSES SIMPAN MASSAL (BULK CREATE) KE DATABASE
    if instances:
        MagneticObservation.objects.bulk_create(instances)
        print(f"\n✅ SUKSES BESAR! Sebanyak {len(instances)} data observasi historis berhasil masuk ke database.")
    else:
        print("\n❌ Gagal: Tidak ada baris data yang valid untuk diimpor. Cek kembali file CSV Anda.")

if __name__ == '__main__':
    import_data()