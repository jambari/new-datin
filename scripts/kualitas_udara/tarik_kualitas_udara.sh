#!/bin/bash
# Tarik data Kualitas Udara (KAH & SPM, "Series data") dari Database Kualitas
# Udara BMKG Jakarta lalu kirim ke API impor di server produksi.
#
# Dijalankan dari PC di jaringan kantor yang menjangkau data center 172.19.1.32
# (produksi tidak menjangkaunya). Cron: setiap tanggal 1, lihat README.md.
#
# Data di pusat diperbarui ±3 bulan sekali (menunggu kiriman sampel), jadi tiap
# kali jalan ditarik MONTHS_BACK bulan ke belakang (default 6) s.d. bulan lalu.
# API hanya menambah data baru: data yang sudah ada dilewati, tidak ditimpa.
#
# Konfigurasi dibaca dari $KU_CONF (default ~/.config/kualitas_udara/datacenter.env,
# chmod 600) berisi:
#   DC_USER=...      # akun Database Kualitas Udara
#   DC_PASS=...
#   API_TOKEN=...    # sama dengan KUALITAS_UDARA_API_TOKEN di .env.production
#   API_URL=https://stageof-jayapura.bmkg.go.id/kualitas-udara/api/import/   (opsional)
set -euo pipefail

KU_CONF=${KU_CONF:-$HOME/.config/kualitas_udara/datacenter.env}
MONTHS_BACK=${MONTHS_BACK:-6}
DC_BASE=${DC_BASE:-http://172.19.1.32:89}
DC_STATION_ID=${DC_STATION_ID:-5051}          # ANGKASAPURA

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

[ -r "$KU_CONF" ] || { log "ERROR: file kredensial $KU_CONF tidak ada"; exit 1; }
# shellcheck disable=SC1090
source "$KU_CONF"
: "${DC_USER:?DC_USER kosong di $KU_CONF}" "${DC_PASS:?DC_PASS kosong di $KU_CONF}" "${API_TOKEN:?API_TOKEN kosong di $KU_CONF}"
API_URL=${API_URL:-https://stageof-jayapura.bmkg.go.id/kualitas-udara/api/import/}

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

# Kirim ke API (token lewat file header agar tidak terlihat di daftar proses).
printf 'Authorization: Token %s\n' "$API_TOKEN" > "$WORK/auth_header"
http=$(curl -sS -m 300 -o "$WORK/response.json" -w '%{http_code}' \
    -H @"$WORK/auth_header" -A "kualitas-udara-sync/1.0 (Stasiun Geofisika Jayapura)" \
    -F "kah=@$WORK/kah_series_data.csv;type=text/csv" \
    -F "spm=@$WORK/spm_series_data.csv;type=text/csv" \
    "$API_URL")
log "API HTTP $http: $(cat "$WORK/response.json")"
[ "$http" = "200" ] || { log "ERROR: impor ke API gagal"; exit 1; }
log "Selesai"
