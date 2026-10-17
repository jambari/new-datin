# Tarik data Kualitas Udara (KAH & SPM)

`tarik_kualitas_udara.sh` mengunduh "Series data" KAH dan SPM stasiun
ANGKASAPURA dari Database Kualitas Udara BMKG Jakarta
(`http://172.19.1.32:89/lab_rata.php`) lalu mengimpornya ke produksi dengan
`manage.py import_kualitas_udara --skip-existing`.

- Jalan di **scproc**: server data center hanya terjangkau dari jaringan ini.
- Rentang: 6 bulan ke belakang s.d. bulan lalu (`MONTHS_BACK`), karena data
  pusat baru diperbarui ±3 bulan sekali.
- Data yang sudah ada di produksi dilewati; hanya minggu/tanggal baru yang masuk.

Kredensial (jangan di-commit) di `~/.config/kualitas_udara/datacenter.env`, chmod 600:

    DC_USER=...
    DC_PASS=...

Cron (scproc, user sysop) — tanggal 1 tiap bulan pukul 07:00 WIB:

    0 7 1 * * /home/sysop/new-datin/scripts/kualitas_udara/tarik_kualitas_udara.sh >> /home/sysop/logs/kualitas_udara_sync.log 2>&1

Jalankan manual: `scripts/kualitas_udara/tarik_kualitas_udara.sh`
(`MONTHS_BACK=12 ...` untuk menarik lebih jauh).
