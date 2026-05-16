#!/usr/bin/env bash
# pull_yolo_progress.sh — Fetch small YOLO training artifacts from the host.
#
# Usage:
#   bash scripts/yolo/pull_yolo_progress.sh
#
# Pulls results.csv, args.yaml, and any *.png/*.jpg plots that exist
# into ./yolo_progress/. Skips weights (~55 MB each); they stay on the host.

set -euo pipefail

REMOTE="sysop@172.21.63.51"
REMOTE_RUN_DIR="/home/sysop/yolo-training/runs/detect/runs/yolov11s_training"
LOCAL_DIR="$(cd "$(dirname "$0")/../.." && pwd)/yolo_progress"

mkdir -p "$LOCAL_DIR"

echo "Pulling from $REMOTE:$REMOTE_RUN_DIR → $LOCAL_DIR"

# Small text artifacts (always expected to exist)
for f in results.csv args.yaml; do
    if scp -q "$REMOTE:$REMOTE_RUN_DIR/$f" "$LOCAL_DIR/$f" 2>/dev/null; then
        echo "  ✓ $f"
    else
        echo "  - $f (not present)"
    fi
done

# Plots and sample images (may not exist until end of training)
for f in results.png confusion_matrix.png confusion_matrix_normalized.png \
         F1_curve.png P_curve.png R_curve.png PR_curve.png \
         labels.jpg labels_correlogram.jpg \
         train_batch0.jpg train_batch1.jpg train_batch2.jpg \
         val_batch0_labels.jpg val_batch0_pred.jpg \
         val_batch1_labels.jpg val_batch1_pred.jpg \
         val_batch2_labels.jpg val_batch2_pred.jpg; do
    if scp -q "$REMOTE:$REMOTE_RUN_DIR/$f" "$LOCAL_DIR/$f" 2>/dev/null; then
        echo "  ✓ $f"
    fi
done

echo
echo "─── current metrics ────────────────────────────────────────────────"
if [[ -f "$LOCAL_DIR/results.csv" ]]; then
    {
        head -1 "$LOCAL_DIR/results.csv" | cut -d, -f1-2,6-9
        tail -1 "$LOCAL_DIR/results.csv" | cut -d, -f1-2,6-9
    } | column -t -s,
fi
