#!/usr/bin/env bash
# psa5_send.sh — Send a single shakemap event's .psa5 file to new-datin API.
#
# Usage:
#   ./psa5_send.sh <event_dir>
#   ./psa5_send.sh /home/sysop/seiscomp3/waveforms/20251016101252_53_2340_13454_40_101252
#
# The script extracts the event_id from the directory name (first 14 chars),
# finds the .psa5 file, and POSTs it to the new-datin API.
# Already-sent events are skipped using a local sent-log.

# ── CONFIG ─────────────────────────────────────────────────────────────────────
DATIN_API_URL="http://36.91.166.189/api/shakemap/psa5/"
DATIN_API_TOKEN="bfca5407ee75ff0a62ac121fb6ff1b1a1c3b348222996125958a5ccb1d0e46c1"
SENT_LOG="/home/sysop/scripts/.psa5_sent.log"
CURL_TIMEOUT=30          # seconds
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

usage() { echo "Usage: $0 <event_dir>"; exit 1; }
[[ $# -lt 1 ]] && usage

EVENT_DIR="${1%/}"          # strip trailing slash
DIR_NAME="$(basename "$EVENT_DIR")"

# ── Get event_id ──────────────────────────────────────────────────────────────
# Primary: read from grid.xml <earthquake id="..."> or event.xml
_get_event_id_from_xml() {
    local dir="$1"
    for xml in "$dir/grid.xml" "$dir/event.xml" "$dir/info.xml"; do
        if [[ -f "$xml" ]]; then
            # Extract id="VALUE" from the first <earthquake ...> element
            local val
            val=$(python3 -c "
import xml.etree.ElementTree as ET, sys
try:
    root = ET.parse('$xml').getroot()
    eq = root.find('.//earthquake') or root.find('earthquake')
    print(eq.get('id', ''))
except: pass
" 2>/dev/null)
            [[ -n "$val" ]] && echo "$val" && return
        fi
    done
    echo ""
}

EVENT_ID=$(_get_event_id_from_xml "$EVENT_DIR")

# Fallback: first 14 characters of the directory name (WIB timestamp)
if [[ -z "$EVENT_ID" ]]; then
    EVENT_ID="${DIR_NAME:0:14}"
fi

if ! [[ "$EVENT_ID" =~ ^[0-9]{14}$ ]]; then
    log "ERROR: Cannot determine valid event_id (got '$EVENT_ID') for $DIR_NAME"
    exit 1
fi

# ── Find .psa5 file ───────────────────────────────────────────────────────────
PSA5_FILE=$(find "$EVENT_DIR" -maxdepth 2 -name "*.psa5" 2>/dev/null | head -1)

if [[ -z "$PSA5_FILE" ]]; then
    log "SKIP: No .psa5 file in $EVENT_DIR"
    exit 0
fi

PSA5_BASENAME="$(basename "$PSA5_FILE")"

# ── Check sent-log ────────────────────────────────────────────────────────────
SENT_KEY="${EVENT_ID}:${PSA5_BASENAME}"
mkdir -p "$(dirname "$SENT_LOG")"
if grep -qxF "$SENT_KEY" "$SENT_LOG" 2>/dev/null; then
    log "SKIP: $SENT_KEY already sent"
    exit 0
fi

# ── POST to new-datin ─────────────────────────────────────────────────────────
log "Sending event_id=$EVENT_ID  file=$PSA5_BASENAME"

RESP_BODY=$(mktemp)
HTTP_CODE=$(curl -s -o "$RESP_BODY" -w "%{http_code}" \
    --max-time "$CURL_TIMEOUT" \
    -X POST "$DATIN_API_URL" \
    -H "Authorization: Bearer $DATIN_API_TOKEN" \
    -F "event_id=${EVENT_ID}" \
    -F "psa5=@${PSA5_FILE}")

RESPONSE=$(cat "$RESP_BODY" 2>/dev/null)
rm -f "$RESP_BODY"

if [[ "$HTTP_CODE" == "200" ]]; then
    log "OK  HTTP=$HTTP_CODE  $RESPONSE"
    echo "$SENT_KEY" >> "$SENT_LOG"
else
    log "ERR HTTP=$HTTP_CODE  $RESPONSE"
    exit 1
fi
