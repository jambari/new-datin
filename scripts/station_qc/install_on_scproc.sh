#!/usr/bin/env bash
# install_on_scproc.sh — install/update the daily station waveform-QC job on scproc.
#
# Run this ON scproc (sysop@192.168.1.5) from a copy of this directory:
#   scp -r scripts/station_qc sysop@192.168.1.5:/tmp/station_qc_src
#   ssh sysop@192.168.1.5 'bash /tmp/station_qc_src/install_on_scproc.sh'
#
# What it does (no sudo needed — follows the other sysop cron jobs on scproc):
#   1. copies station_qc.py to ~/station_qc/
#   2. adds/replaces one crontab line: every day 08:40 WIB = 01:40 UTC
#      (scproc runs in Asia/Jakarta, WIB = UTC+7; .189 sends the report at 02:30 UTC),
#      processes the previous UTC day and POSTs to new-datin /qc/api/station-daily/
#      using QC_API_URL / QC_API_TOKEN / REQUESTS_CA_BUNDLE from /etc/seiscomp-qc/watcher.env
#
# Backfill once after installing (about 75 s per day):
#   set -a; . /etc/seiscomp-qc/watcher.env; set +a
#   nice -n 15 /opt/seiscomp_qc/.venv/bin/python ~/station_qc/station_qc.py --day yesterday --backfill 60 --post
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/station_qc"
PY=/opt/seiscomp_qc/.venv/bin/python
ENV_FILE=/etc/seiscomp-qc/watcher.env
LOG="$HOME/logs/station_qc.log"
MARK="# station_qc daily (new-datin qc_review)"
LINE="40 8 * * * set -a; . $ENV_FILE; set +a; nice -n 15 $PY $DEST/station_qc.py --day yesterday --post >> $LOG 2>&1 $MARK"

[[ -r "$ENV_FILE" ]] || { echo "cannot read $ENV_FILE" >&2; exit 1; }
[[ -x "$PY" ]] || { echo "missing $PY" >&2; exit 1; }

mkdir -p "$DEST" "$(dirname "$LOG")"
install -m 0755 "$SRC/station_qc.py" "$DEST/station_qc.py"
echo "installed $DEST/station_qc.py"

# Replace any previous station_qc line (schedule may have changed), keep the rest.
current="$(crontab -l 2>/dev/null | grep -vF "$MARK" || true)"
printf '%s\n%s\n' "$current" "$LINE" | sed '/^$/d' | crontab -
echo "crontab entry:"
crontab -l | grep -F "$MARK"
