# Indeks K & A JYP — hitung sendiri (metode FMI)

Jayapura menghitung indeks K/A sendiri dari data mentah magnetometer LEMI-018, tanpa
bergantung pada citra `dataweb.bmkg.go.id` (citra BMKG tetap diambil sebagai pembanding).

## Alur data

1. **PC LEMI (172.21.63.105)** — task `LEMIRawSync` (tiap jam, :05) menjalankan
   `C:\lemi_raw_sync\lemi_raw_sync.ps1` (salinan `scripts/lemi_raw_sync.ps1`). Skrip menanyakan
   daftar berkas server lalu mengirim berkas `D:\lemi018\YYYY MM DD hh mm ss.txt` 30 hari terakhir
   yang belum ada / lebih kecil di server. Hari yang terlewat otomatis disusul.
   Token = `LEMI_MONITOR_TOKEN` (berkas `C:\lemi_raw_sync\token.txt`, tidak di repo).
2. **API** `GET/POST /magnet/api/lemi/raw/` (`magnet.views.lemi_raw_api`) menyimpan ke
   `LEMI_RAW_DIR` (default `private_media/lemi_raw/`, tidak dilayani nginx) dan memicu hitung ulang.
3. **Celery**: `compute-kindex-jyp-hourly` (menit :20) menghitung kemarin lusa s.d. hari ini;
   `send-kindex-jyp-daily` 16:00 WIT mengirim grafik K & A ke grup Telegram.
4. Hasil di `KIndexDaily` dengan `sumber='lokal'`; parser citra BMKG tidak menimpanya.
   Hari sebelum `KINDEX_FMI_START` (data Excel stasiun) tidak disentuh.

## Metode (`magnet/kindex_fmi.py`)

Port kode C FMI (Sucksdorff dkk. 1991) via MagPy: K sementara dari rentang X/Y per 3 jam →
rata-rata jam berjendela ±(30 + n + K^3.3) menit → Sr = Fourier orde 5 → K dari rentang (data − Sr),
diulang. Data 1 detik dijadikan median per menit (buang lonjakan sesaat); loncatan baseline buatan
(> 100 nT antar menit, mis. perawatan sensor 11 Okt 2026 09:00 UTC, Y −2995 nT) dikosongkan dan
level sesudahnya disamakan. Hari D dihitung dengan data D−1 dan D+1; tanpa D+1 hasilnya "Sementara".

**L9 = 240 nT** (`KINDEX_JYP_L9`): dicocokkan dengan K citra BMKG 3–24 Okt 2026 (tanpa 10–11 Okt
yang terganggu loncatan baseline): bias ≈ 0, 99 % selisih ≤ 1, korelasi dengan Kp NOAA 0,68
(citra BMKG 0,44).

## Perintah

    python manage.py compute_kindex_jyp --start 2026-10-03 --end 2026-10-31   # isi ulang
    python manage.py compute_kindex_jyp --start 2026-10-10 --end 2026-10-12 --l9 260 --dry-run
