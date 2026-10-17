#!/bin/bash
# Tarik data Kualitas Udara (KAH & SPM, "Series data") dari Database Kualitas
# Udara BMKG Jakarta lalu impor ke server produksi.
#
# Dijalankan dari scproc (server data center 172.19.1.32 hanya terjangkau dari
# jaringan ini, tidak dari produksi). Cron: setiap tanggal 1, lihat README.md.
#
# Data di pusat diperbarui ±3 bulan sekali (menunggu kiriman sampel), jadi tiap
# kali jalan ditarik MONTHS_BACK bulan ke belakang (default 6) s.d. bulan lalu.
# Di produksi diimpor dengan --skip-existing: data yang sudah ada dilewati,
# hanya minggu/tanggal yang belum ada yang dimasukkan.
#
# Kredensial dibaca dari $KU_CONF (default ~/.config/kualitas_udara/datacenter.env,
# chmod 600) berisi:
#   DC_USER=...
#   DC_PASS=...
set -euo pipefail

KU_CONF=${KU_CONF:-$HOME/.config/kualitas_udara/datacenter.env}
MONTHS_BACK=${MONTHS_BACK:-6}
DC_BASE=${DC_BASE:-http://172.19.1.32:89}
DC_STATION_ID=${DC_STATION_ID:-5051}          # ANGKASAPURA
PROD=${PROD:-sysop@36.91.166.189}
PROD_DIR=${PROD_DIR:-/var/www/html}

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

[ -r "$KU_CONF" ] || { log "ERROR: file kredensial $KU_CONF tidak ada"; exit 1; }
# shellcheck disable=SC1090
source "$KU_CONF"
: "${DC_USER:?DC_USER kosong di $KU_CONF}" "${DC_PASS:?DC_PASS kosong di $KU_CONF}"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
chmod 700 "$WORK"
JAR="$WORK/cookies.txt"

first_of_month=$(date +%Y-%m-01)
START=$(date -d "$first_of_month -$MONTHS_BACK month" +%m/%Y)
END=$(date -d "$first_of_month -1 month" +%m/%Y)
log "Periode tarik: $START s.d. $END"

# Login (password lewat file agar tidak terlihat di daftar proses).
printf '%s' "$DC_USER" > "$WORK/user"; printf '%s' "$DC_PASS" > "$WORK/pass"
home=$(curl -sS -m 60 -L -c "$JAR" -b "$JAR" \
    --data-urlencode "txtUserID@$WORK/user" --data-urlencode "txtPwdBaru@$WORK/pass" \
    --data "cmdLogin=" "$DC_BASE/xlogin.php")
rm -f "$WORK/user" "$WORK/pass"
if ! grep -q "Selamat datang" <<<"$home"; then
    log "ERROR: login ke $DC_BASE gagal"; exit 1
fi

declare -A HEADER=(
    [kah]="stasiun,bulan,minggu,PH,DH,CA,MG,NA,K,NH4,CL,SO4,NO3,KT,AC,AL,CH,OX"
    [spm]="stasiun,timestamp,SPM"
)
for param in kah spm; do
    out="$WORK/${param}_series_data.csv"
    curl -sS -m 300 -b "$JAR" -o "$out" \
        --data "cboParam=$param" --data-urlencode "cboStasiun[]=$DC_STATION_ID" \
        --data "cboJenis=series" --data-urlencode "tanggal_laporan=$START" \
        --data-urlencode "tanggal_laporan2=$END" --data "cmdReport=DOWNLOAD" \
        "$DC_BASE/LAB/dl_lab.php"
    if [ "$(head -1 "$out" | tr -d '\r')" != "${HEADER[$param]}" ]; then
        log "ERROR: unduhan $param bukan CSV yang diharapkan: $(head -c 200 "$out")"; exit 1
    fi
    log "Unduh $param: $(( $(wc -l < "$out") - 1 )) baris"
done

remote=$(ssh -o BatchMode=yes "$PROD" 'mktemp -d /tmp/ku_sync.XXXXXX')
scp -q -o BatchMode=yes "$WORK/kah_series_data.csv" "$WORK/spm_series_data.csv" "$PROD:$remote/"
ssh -o BatchMode=yes "$PROD" "cd '$PROD_DIR' && ENVIRONMENT=production venv/bin/python manage.py import_kualitas_udara \
    --kah '$remote/kah_series_data.csv' --spm '$remote/spm_series_data.csv' --skip-existing 2>&1 \
    | grep -v 'objects imported'; status=\${PIPESTATUS[0]}; rm -rf '$remote'; exit \$status"
log "Selesai"
