#!/usr/bin/env bash
# psa5_send.sh — Send one or all .psa5 files for a shakemap event to new-datin API.
#
# Usage:
#   ./psa5_send.sh <psa5_file>        # send a single file
#   ./psa5_send.sh --dir <event_dir>  # send every .psa5 in an event directory
#
# Each .psa5 file is a single station-component for one event. Station code,
# component, and event timestamp are extracted from the filename:
#   <YYYYMMDDhhmmss>_<NET>_<STA>_<COMP>_BP4_*.psa5
#
# Already-sent files are skipped via a local sent-log.

# ── CONFIG ─────────────────────────────────────────────────────────────────────
DATIN_API_URL="http://36.91.166.189/api/shakemap/psa5/"
DATIN_API_TOKEN="bfca5407ee75ff0a62ac121fb6ff1b1a1c3b348222996125958a5ccb1d0e46c1"
SENT_LOG="/home/sysop/scripts/.psa5_sent.log"
CURL_TIMEOUT=30
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

usage() {
    echo "Usage: $0 <psa5_file>"
    echo "       $0 --dir <event_dir>"
    exit 1
}

send_one() {
    local psa5="$1"
    local base="$(basename "$psa5")"

    # Filename: <event_ts_utc>_<NET>_<STA>_<COMP>_BP4_0.1_40.psa5
    IFS='_' read -r EVENT_TS_UTC NETWORK STATION COMPONENT _REST <<< "$base"

    if ! [[ "$EVENT_TS_UTC" =~ ^[0-9]{14}$ ]] || [[ -z "$STATION" || -z "$COMPONENT" ]]; then
        log "SKIP: cannot parse station/component from $base"
        return 0
    fi

    # Convert UTC timestamp → WIB (+7h) to match ShakemapEvent.event_id format.
    EVENT_TS=$(date -d "${EVENT_TS_UTC:0:4}-${EVENT_TS_UTC:4:2}-${EVENT_TS_UTC:6:2} ${EVENT_TS_UTC:8:2}:${EVENT_TS_UTC:10:2}:${EVENT_TS_UTC:12:2} UTC +7 hours" "+%Y%m%d%H%M%S" 2>/dev/null)
    if [[ -z "$EVENT_TS" ]]; then
        log "SKIP: failed UTC→WIB conversion of $EVENT_TS_UTC"
        return 0
    fi

    local sent_key="${EVENT_TS}:${STATION}:${COMPONENT}:${base}"
    mkdir -p "$(dirname "$SENT_LOG")"
    if grep -qxF "$sent_key" "$SENT_LOG" 2>/dev/null; then
        log "SKIP: $sent_key already sent"
        return 0
    fi

    log "Sending event=$EVENT_TS sta=$STATION comp=$COMPONENT file=$base"

    local resp_body
    resp_body=$(mktemp)
    local http_code
    http_code=$(curl -s -o "$resp_body" -w "%{http_code}" \
        --max-time "$CURL_TIMEOUT" \
        -X POST "$DATIN_API_URL" \
        -H "Authorization: Bearer $DATIN_API_TOKEN" \
        -F "event_id=${EVENT_TS}" \
        -F "station_code=${STATION}" \
        -F "component=${COMPONENT}" \
        -F "psa5=@${psa5}")
    local resp
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
    if [[ ! -d "$EVENT_DIR" ]]; then
        log "ERROR: not a directory: $EVENT_DIR"
        exit 1
    fi
    rc=0
    while IFS= read -r f; do
        send_one "$f" || rc=$?
    done < <(find "$EVENT_DIR" -maxdepth 1 -name "*.psa5" -type f | sort)
    exit "$rc"
else
    PSA5="$1"
    if [[ ! -f "$PSA5" ]]; then
        log "ERROR: file not found: $PSA5"
        exit 1
    fi
    send_one "$PSA5"
fi
