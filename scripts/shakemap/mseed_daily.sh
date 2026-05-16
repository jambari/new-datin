#!/usr/bin/env bash
# mseed_daily.sh — Daily catch-up: scan all event directories and send any unsent .mseed files.
#
# Cron setup (runs at 01:00 WIB):
#   0 1 * * * /home/sysop/scripts/mseed_daily.sh >> /home/sysop/scripts/mseed_daily.log 2>&1
#
# Use --days N to limit scan to the last N days (default 30).
# Use --all to scan every event directory regardless of age.

# ── CONFIG ─────────────────────────────────────────────────────────────────────
WAVEFORMS_DIR="/home/sysop/seiscomp3/shakemaps_waveform_spectra/waveforms"
SEND_SCRIPT="/home/sysop/scripts/mseed_send.sh"
DEFAULT_DAYS=30
# ──────────────────────────────────────────────────────────────────────────────

set -uo pipefail

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

DAYS="$DEFAULT_DAYS"
SCAN_ALL=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --all)         SCAN_ALL=true; shift ;;
        --days=*)      DAYS="${1#--days=}"; shift ;;
        --days)        shift; DAYS="${1:-$DEFAULT_DAYS}"; shift ;;
        *)             shift ;;
    esac
done

log "=== mseed_daily.sh started (scan_all=$SCAN_ALL days=$DAYS) ==="

if [[ ! -d "$WAVEFORMS_DIR" ]]; then
    log "ERROR: waveforms dir not found: $WAVEFORMS_DIR"
    exit 1
fi

FIND_ARGS=("$WAVEFORMS_DIR" -maxdepth 1 -type d)
FIND_ARGS+=(-regextype posix-extended -regex ".*/[0-9]{14}_.*")
if [[ "$SCAN_ALL" == false ]]; then
    FIND_ARGS+=(-mtime "-${DAYS}")
fi

TOTAL_DIRS=0
TOTAL_FILES=0
SENT=0
SKIPPED=0
ERRORS=0

while IFS= read -r -d '' EVENT_DIR; do
    TOTAL_DIRS=$((TOTAL_DIRS + 1))

    while IFS= read -r MSEED; do
        TOTAL_FILES=$((TOTAL_FILES + 1))
        OUTPUT=$(bash "$SEND_SCRIPT" "$MSEED" 2>&1)
        STATUS=$?
        echo "$OUTPUT"

        if echo "$OUTPUT" | grep -q "SKIP:"; then
            SKIPPED=$((SKIPPED + 1))
        elif [[ $STATUS -eq 0 ]]; then
            SENT=$((SENT + 1))
        else
            ERRORS=$((ERRORS + 1))
        fi
    done < <(find "$EVENT_DIR" -maxdepth 1 -name "*.mseed" -type f | sort)

done < <(find "${FIND_ARGS[@]}" -print0 2>/dev/null | sort -z)

log "=== Done: dirs=$TOTAL_DIRS  files=$TOTAL_FILES  sent=$SENT  skipped=$SKIPPED  errors=$ERRORS ==="
