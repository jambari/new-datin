#!/usr/bin/env bash
# psa5_daily.sh — Daily catch-up: scan all event directories and send any unsent .psa5 files.
#
# Cron setup (runs at 01:00 WIB):
#   0 1 * * * /home/sysop/scripts/psa5_daily.sh >> /home/sysop/scripts/psa5_daily.log 2>&1
#
# Use --days N to limit scan to the last N days (default 30).
# Use --all to scan every event directory regardless of age.

# ── CONFIG ─────────────────────────────────────────────────────────────────────
SPECTRA_DIR="/home/sysop/seiscomp3/shakemaps_waveform_spectra/spectra"
SEND_SCRIPT="/home/sysop/scripts/psa5_send.sh"
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

log "=== psa5_daily.sh started (scan_all=$SCAN_ALL days=$DAYS) ==="

if [[ ! -d "$SPECTRA_DIR" ]]; then
    log "ERROR: spectra dir not found: $SPECTRA_DIR"
    exit 1
fi

FIND_ARGS=("$SPECTRA_DIR" -maxdepth 1 -type d)
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
    DIR_NAME="$(basename "$EVENT_DIR")"

    while IFS= read -r PSA5; do
        TOTAL_FILES=$((TOTAL_FILES + 1))
        OUTPUT=$(bash "$SEND_SCRIPT" "$PSA5" 2>&1)
        STATUS=$?
        echo "$OUTPUT"

        if echo "$OUTPUT" | grep -q "SKIP:"; then
            SKIPPED=$((SKIPPED + 1))
        elif [[ $STATUS -eq 0 ]]; then
            SENT=$((SENT + 1))
        else
            ERRORS=$((ERRORS + 1))
        fi
    done < <(find "$EVENT_DIR" -maxdepth 1 -name "*.psa5" -type f | sort)

done < <(find "${FIND_ARGS[@]}" -print0 2>/dev/null | sort -z)

log "=== Done: dirs=$TOTAL_DIRS  files=$TOTAL_FILES  sent=$SENT  skipped=$SKIPPED  errors=$ERRORS ==="
