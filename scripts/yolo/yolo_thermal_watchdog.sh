#!/usr/bin/env bash
# yolo_thermal_watchdog.sh — Train YOLO intermittently, gated by GPU temperature.
#
# - Pauses (SIGINT) the training process when GPU temp >= HOT_TEMP
# - Resumes from `last.pt` when GPU temp <= COOL_TEMP and training is not running
# - Exits cleanly when results.csv last epoch >= TARGET_EPOCHS
#
# Run via:
#   nohup bash /home/sysop/scripts/yolo_thermal_watchdog.sh \
#       >> /home/sysop/yolo-training/thermal_watchdog.log 2>&1 &

# ── CONFIG ──────────────────────────────────────────────────────────────────
YOLO_DIR="/home/sysop/yolo-training"
RUN_DIR="$YOLO_DIR/runs/detect/runs/yolov11s_training"
WEIGHTS="$RUN_DIR/weights/last.pt"
RESULTS_CSV="$RUN_DIR/results.csv"
TRAIN_LOG="$YOLO_DIR/train_resume.log"
ARCHIVE_BASE="/home/sysop/Documents"   # final archive lands at $ARCHIVE_BASE/yolov11s_<timestamp>/
HOT_TEMP=87       # pause at or above this (°C)
COOL_TEMP=78      # resume at or below this (°C)
CHECK_INTERVAL=30 # seconds between polls
TARGET_EPOCHS=200
GRACEFUL_WAIT=30  # seconds to wait for SIGINT to land
# ─────────────────────────────────────────────────────────────────────────────

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

get_temp() {
    nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits | head -1 | tr -d ' '
}

# Match the python that owns the train loop (parent of any workers).
train_pid() {
    pgrep -f "python3.*ultralytics.*resume=True|YOLO.*resume=True" 2>/dev/null | head -1
}

last_epoch_done() {
    [[ -f "$RESULTS_CSV" ]] || { echo 0; return; }
    # First column = epoch number; last row = most recent completed epoch.
    tail -1 "$RESULTS_CSV" | cut -d, -f1 | tr -d ' '
}

start_training() {
    log "STARTING training (temp $(get_temp)°C, last epoch $(last_epoch_done))"
    cd "$YOLO_DIR" || { log "ERROR: cd $YOLO_DIR failed"; return 1; }
    nohup python3 -c "from ultralytics import YOLO; m = YOLO('$WEIGHTS'); m.train(resume=True)" \
        >> "$TRAIN_LOG" 2>&1 &
    disown
    sleep 5
    local pid
    pid=$(train_pid)
    log "  spawned pid=${pid:-unknown}"
}

archive_run() {
    local stamp dest
    stamp=$(date +%Y%m%d_%H%M%S)
    dest="${ARCHIVE_BASE}/yolov11s_${stamp}"
    log "ARCHIVING run dir → $dest"
    mkdir -p "$dest" || { log "  ERROR: mkdir failed"; return 1; }
    if cp -r "$RUN_DIR"/. "$dest/"; then
        log "  archive complete ($(du -sh "$dest" | cut -f1))"
    else
        log "  ERROR: cp failed"
        return 1
    fi
}

stop_training() {
    local pid
    pid=$(train_pid)
    if [[ -z "$pid" ]]; then
        log "stop_training: no PID found, already stopped"
        return
    fi
    log "STOPPING pid=$pid (temp $(get_temp)°C)"
    kill -INT "$pid" 2>/dev/null
    for ((i=1; i<=GRACEFUL_WAIT; i++)); do
        kill -0 "$pid" 2>/dev/null || { log "  exited after ${i}s"; return; }
        sleep 1
    done
    log "  WARN: still running after ${GRACEFUL_WAIT}s, sending SIGTERM"
    kill -TERM "$pid" 2>/dev/null
}

# ── Main loop ────────────────────────────────────────────────────────────────
log "===== watchdog start (HOT=${HOT_TEMP}°C COOL=${COOL_TEMP}°C target=${TARGET_EPOCHS} epochs) ====="

# Trap so SIGTERM/SIGINT to the watchdog also stops training cleanly.
trap 'log "watchdog received signal, stopping training"; stop_training; exit 0' INT TERM

while true; do
    epoch=$(last_epoch_done)
    if (( epoch >= TARGET_EPOCHS )); then
        log "DONE: last epoch=$epoch >= target=$TARGET_EPOCHS — stopping watchdog"
        stop_training
        archive_run
        exit 0
    fi

    temp=$(get_temp)
    pid=$(train_pid)
    if [[ -n "$pid" ]]; then
        # Currently training
        if [[ "$temp" =~ ^[0-9]+$ ]] && (( temp >= HOT_TEMP )); then
            log "HOT: temp=${temp}°C >= ${HOT_TEMP}°C — pausing (epoch $epoch)"
            stop_training
        fi
    else
        # Not training
        if [[ "$temp" =~ ^[0-9]+$ ]] && (( temp <= COOL_TEMP )); then
            log "COOL: temp=${temp}°C <= ${COOL_TEMP}°C — resuming"
            start_training
        else
            log "idle: temp=${temp}°C, waiting for <= ${COOL_TEMP}°C (epoch $epoch/$TARGET_EPOCHS)"
        fi
    fi

    sleep "$CHECK_INTERVAL"
done
