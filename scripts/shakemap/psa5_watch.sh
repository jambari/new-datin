#!/usr/bin/env bash
# psa5_watch.sh — Real-time watcher: send .psa5 files as soon as shakemap writes them.
#
# Requires inotify-tools:
#   sudo apt install inotify-tools
#
# Run as a service (see psa5-watcher.service) or manually:
#   bash psa5_watch.sh
#
# The watcher fires when SeisComP3 finishes writing a .psa5 file (close_write event).

# ── CONFIG ─────────────────────────────────────────────────────────────────────
WAVEFORMS_DIR="/home/sysop/seiscomp3/waveforms"
SEND_SCRIPT="/home/sysop/scripts/psa5_send.sh"
LOG_FILE="/home/sysop/scripts/psa5_watch.log"
WRITE_SETTLE_SECS=3      # brief wait after close_write to ensure flush
# ──────────────────────────────────────────────────────────────────────────────

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

if ! command -v inotifywait &>/dev/null; then
    echo "ERROR: inotify-tools not installed. Run: sudo apt install inotify-tools"
    exit 1
fi

log "PSA5 watcher started. Watching $WAVEFORMS_DIR …"

# Watch for close_write events on .psa5 files, recursively
inotifywait -m -r -e close_write \
    --format '%w%f' \
    --includei '\.psa5$' \
    "$WAVEFORMS_DIR" 2>/dev/null \
| while IFS= read -r FILEPATH; do

    EVENT_DIR="$(dirname "$FILEPATH")"
    log "New .psa5 detected: $FILEPATH"

    # Settle: let shakemap finish any remaining writes in the same directory
    sleep "$WRITE_SETTLE_SECS"

    # Run send in background so watcher never blocks
    bash "$SEND_SCRIPT" "$EVENT_DIR" >> "$LOG_FILE" 2>&1 &

done
