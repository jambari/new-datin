#!/usr/bin/env bash
# mseed_send.sh — Send one .mseed file to the new-datin waveform API.
#
# Usage:
#   ./mseed_send.sh <mseed_file>
#   ./mseed_send.sh --dir <event_dir>
#
# Each .mseed file is a single station-component for one event. Station code,
# component, and event timestamp are extracted from the filename:
#   <YYYYMMDDhhmmss_utc>_<NET>_<STA>_<COMP>_BP4_*.mseed
# The UTC timestamp is converted to WIB (+7 h) so prod stores under the same
# event_id as the matching .psa5.

# ── CONFIG ─────────────────────────────────────────────────────────────────────
DATIN_API_URL="http://36.91.166.189/api/shakemap/waveform/"
DATIN_API_TOKEN="bfca5407ee75ff0a62ac121fb6ff1b1a1c3b348222996125958a5ccb1d0e46c1"
SENT_LOG="/home/sysop/scripts/.mseed_sent.log"
CURL_TIMEOUT=60          # mseed POSTs are larger than psa5, allow more time
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

usage() {
    echo "Usage: $0 <mseed_file>"
    echo "       $0 --dir <event_dir>"
    exit 1
}

send_one() {
    local mseed="$1"
    local base
    base="$(basename "$mseed")"

    # Filename: <event_ts_utc>_<NET>_<STA>_<COMP>_BP4_<lf>_<hf>.mseed
    IFS='_' read -r EVENT_TS_UTC NETWORK STATION COMPONENT _REST <<< "$base"

    if ! [[ "$EVENT_TS_UTC" =~ ^[0-9]{14}$ ]] || [[ -z "$STATION" || -z "$COMPONENT" ]]; then
        log "SKIP: cannot parse station/component from $base"
        return 0
    fi

    local epoch_utc
    epoch_utc=$(date -d "${EVENT_TS_UTC:0:4}-${EVENT_TS_UTC:4:2}-${EVENT_TS_UTC:6:2} ${EVENT_TS_UTC:8:2}:${EVENT_TS_UTC:10:2}:${EVENT_TS_UTC:12:2} UTC" "+%s" 2>/dev/null)
    if [[ -z "$epoch_utc" ]]; then
        log "SKIP: failed UTC parse of $EVENT_TS_UTC"
        return 0
    fi
    EVENT_TS=$(date -u -d "@$((epoch_utc + 25200))" "+%Y%m%d%H%M%S")

    local sent_key="${EVENT_TS}:${STATION}:${COMPONENT}:${base}"
    mkdir -p "$(dirname "$SENT_LOG")"
    if grep -qxF "$sent_key" "$SENT_LOG" 2>/dev/null; then
        log "SKIP: $sent_key already sent"
        return 0
    fi

    log "Sending event=$EVENT_TS sta=$STATION comp=$COMPONENT file=$base"

    local resp_body http_code resp
    resp_body=$(mktemp)
    http_code=$(curl -s -o "$resp_body" -w "%{http_code}" \
        --max-time "$CURL_TIMEOUT" \
        -X POST "$DATIN_API_URL" \
        -H "Authorization: Bearer $DATIN_API_TOKEN" \
        -F "event_id=${EVENT_TS}" \
        -F "station_code=${STATION}" \
        -F "component=${COMPONENT}" \
        -F "mseed=@${mseed}")
    resp=$(cat "$resp_body" 2>/dev/null)
    rm -f "$resp_body"

    if [[ "$http_code" == "200" ]]; then
        log "OK  HTTP=$http_code  $resp"
        echo "$sent_key" >> "$SENT_LOG"
    else
        log "ERR HTTP=$http_code  $resp"
        return 1
    fi
}

[[ $# -lt 1 ]] && usage

if [[ "$1" == "--dir" ]]; then
    [[ $# -lt 2 ]] && usage
    EVENT_DIR="${2%/}"
    [[ ! -d "$EVENT_DIR" ]] && { log "ERROR: not a directory: $EVENT_DIR"; exit 1; }
    rc=0
    while IFS= read -r f; do
        send_one "$f" || rc=$?
    done < <(find "$EVENT_DIR" -maxdepth 1 -name "*.mseed" -type f | sort)
    exit "$rc"
else
    MSEED="$1"
    [[ ! -f "$MSEED" ]] && { log "ERROR: file not found: $MSEED"; exit 1; }
    send_one "$MSEED"
fi
