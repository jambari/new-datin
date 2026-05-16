#!/usr/bin/env bash
# psa5_watch.sh — Real-time watcher: send each .psa5 file as soon as shakemap writes it.
#
# Requires inotify-tools:  sudo apt install inotify-tools
#
# Run as a service (see psa5-watcher.service) or manually:
#   bash psa5_watch.sh

# ── CONFIG ─────────────────────────────────────────────────────────────────────
SPECTRA_DIR="/home/sysop/seiscomp3/shakemaps_waveform_spectra/spectra"
SEND_SCRIPT="/home/sysop/scripts/psa5_send.sh"
LOG_FILE="/home/sysop/scripts/psa5_watch.log"
WRITE_SETTLE_SECS=2
# ──────────────────────────────────────────────────────────────────────────────

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

if ! command -v inotifywait &>/dev/null; then
    echo "ERROR: inotify-tools not installed. Run: sudo apt install inotify-tools"
    exit 1
fi

if [[ ! -d "$SPECTRA_DIR" ]]; then
    log "ERROR: spectra dir not found: $SPECTRA_DIR"
    exit 1
fi

log "PSA5 watcher started. Watching $SPECTRA_DIR …"

inotifywait -m -r -e close_write --format '%w%f' "$SPECTRA_DIR" \
| while IFS= read -r FILEPATH; do
    [[ "$FILEPATH" =~ \.psa5$ ]] || continue
    log "New .psa5 detected: $FILEPATH"
    sleep "$WRITE_SETTLE_SECS"
    bash "$SEND_SCRIPT" "$FILEPATH" >> "$LOG_FILE" 2>&1 &
done
