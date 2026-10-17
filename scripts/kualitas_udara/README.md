# Tarik data Kualitas Udara (KAH & SPM)

`tarik_kualitas_udara.sh` mengunduh "Series data" KAH dan SPM stasiun
ANGKASAPURA dari Database Kualitas Udara BMKG Jakarta
(`http://172.19.1.32:89/lab_rata.php`) lalu mengirimnya ke API produksi
`POST /kualitas-udara/api/import/` (header `Authorization: Token ...`).

- Jalan di **scclient (192.168.1.7)**, PC kantor yang menyala 24 jam dan
  menjangkau data center (produksi tidak menjangkaunya).
- Rentang: 6 bulan ke belakang s.d. bulan lalu (`MONTHS_BACK`), karena data
  pusat baru diperbarui ±3 bulan sekali.
- API hanya menambah data baru; data yang sudah ada dilewati, tidak ditimpa.
  API nonaktif bila `KUALITAS_UDARA_API_TOKEN` di `.env.production` kosong.

Konfigurasi (jangan di-commit) di `~/.config/kualitas_udara/datacenter.env`, chmod 600:

    DC_USER=...
    DC_PASS=...
    API_TOKEN=...

Cron (scclient, user sysop) — tanggal 1 tiap bulan pukul 08:00 WIT:

    0 8 1 * * $HOME/kualitas_udara/tarik_kualitas_udara.sh >> $HOME/logs/kualitas_udara_sync.log 2>&1

Jalankan manual: `~/kualitas_udara/tarik_kualitas_udara.sh`
(`MONTHS_BACK=12 ...` untuk menarik lebih jauh).

Impor manual di produksi (menimpa data lama bila tanpa `--skip-existing`):

    ENVIRONMENT=production venv/bin/python manage.py import_kualitas_udara --kah file.csv --spm file.csv [--skip-existing]
