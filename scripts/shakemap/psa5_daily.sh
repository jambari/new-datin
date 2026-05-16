#!/usr/bin/env bash
# psa5_daily.sh — Daily catch-up: scan all event directories and send any unsent .psa5 files.
#
# Cron setup (runs at 01:00 WIB = 18:00 UTC, every day):
#   0 18 * * * /home/sysop/scripts/psa5_daily.sh >> /home/sysop/scripts/psa5_daily.log 2>&1
#
# Or if the machine runs on WIB:
#   0 1 * * * /home/sysop/scripts/psa5_daily.sh >> /home/sysop/scripts/psa5_daily.log 2>&1
#
# Use --days N to limit scan to the last N days (default 30).
# Use --all to scan every event directory regardless of age.

# ── CONFIG ─────────────────────────────────────────────────────────────────────
WAVEFORMS_DIR="/home/sysop/seiscomp3/waveforms"
SEND_SCRIPT="/home/sysop/scripts/psa5_send.sh"
DEFAULT_DAYS=30
# ──────────────────────────────────────────────────────────────────────────────

set -uo pipefail

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# Parse arguments
DAYS="$DEFAULT_DAYS"
SCAN_ALL=false
for arg in "$@"; do
    case "$arg" in
        --all)         SCAN_ALL=true ;;
        --days=*)      DAYS="${arg#--days=}" ;;
        --days)        shift; DAYS="${1:-$DEFAULT_DAYS}" ;;
    esac
done

log "=== psa5_daily.sh started (scan_all=$SCAN_ALL days=$DAYS) ==="

# Build find command
FIND_ARGS=("$WAVEFORMS_DIR" -maxdepth 1 -type d)
# Directory names match: 14-digit timestamp followed by underscore
FIND_ARGS+=(-regextype posix-extended -regex ".*/[0-9]{14}_.*")
if [[ "$SCAN_ALL" == false ]]; then
    FIND_ARGS+=(-mtime "-${DAYS}")
fi

TOTAL=0
SENT=0
SKIPPED=0
ERRORS=0

while IFS= read -r -d '' EVENT_DIR; do
    TOTAL=$((TOTAL + 1))
    DIR_NAME="$(basename "$EVENT_DIR")"

    # Check if directory contains a .psa5 file at all (fast check before calling send)
    if ! find "$EVENT_DIR" -maxdepth 2 -name "*.psa5" -quit 2>/dev/null | grep -q .; then
        log "SKIP (no .psa5): $DIR_NAME"
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    OUTPUT=$(bash "$SEND_SCRIPT" "$EVENT_DIR" 2>&1)
    STATUS=$?
    echo "$OUTPUT"

    if echo "$OUTPUT" | grep -q "^.*SKIP:"; then
        SKIPPED=$((SKIPPED + 1))
    elif [[ $STATUS -eq 0 ]]; then
        SENT=$((SENT + 1))
    else
        ERRORS=$((ERRORS + 1))
    fi

done < <(find "${FIND_ARGS[@]}" -print0 2>/dev/null | sort -z)

log "=== Done: scanned=$TOTAL  sent=$SENT  skipped=$SKIPPED  errors=$ERRORS ==="
