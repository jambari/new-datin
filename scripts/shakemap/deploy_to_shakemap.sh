#!/usr/bin/env bash
# deploy_to_shakemap.sh — Deploy PSA5 scripts to the SeisComP3 shakemap machine.
#
# Run this from new-datin development machine:
#   bash scripts/shakemap/deploy_to_shakemap.sh
#
# After running, SSH into the machine and follow the post-install steps printed at the end.

SHAKEMAP_HOST="172.21.63.50"
SHAKEMAP_USER="sysop"
REMOTE_SCRIPTS_DIR="/home/sysop/scripts"
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

log "Deploying PSA5 scripts to ${SHAKEMAP_USER}@${SHAKEMAP_HOST}:${REMOTE_SCRIPTS_DIR}/"

# Create remote scripts directory
ssh "${SHAKEMAP_USER}@${SHAKEMAP_HOST}" "mkdir -p ${REMOTE_SCRIPTS_DIR}"

# Copy scripts
scp "$SCRIPTS_DIR/psa5_send.sh"   "${SHAKEMAP_USER}@${SHAKEMAP_HOST}:${REMOTE_SCRIPTS_DIR}/"
scp "$SCRIPTS_DIR/psa5_watch.sh"  "${SHAKEMAP_USER}@${SHAKEMAP_HOST}:${REMOTE_SCRIPTS_DIR}/"
scp "$SCRIPTS_DIR/psa5_daily.sh"  "${SHAKEMAP_USER}@${SHAKEMAP_HOST}:${REMOTE_SCRIPTS_DIR}/"
scp "$SCRIPTS_DIR/mseed_send.sh"  "${SHAKEMAP_USER}@${SHAKEMAP_HOST}:${REMOTE_SCRIPTS_DIR}/"

# Make executable
ssh "${SHAKEMAP_USER}@${SHAKEMAP_HOST}" \
    "chmod +x ${REMOTE_SCRIPTS_DIR}/psa5_send.sh ${REMOTE_SCRIPTS_DIR}/psa5_watch.sh ${REMOTE_SCRIPTS_DIR}/psa5_daily.sh ${REMOTE_SCRIPTS_DIR}/mseed_send.sh"

# Copy systemd service (requires sudo on remote)
scp "$SCRIPTS_DIR/psa5-watcher.service" \
    "${SHAKEMAP_USER}@${SHAKEMAP_HOST}:/tmp/psa5-watcher.service"

log "Files deployed."

cat <<'EOF'

════════════════════════════════════════════════════════════════
 POST-INSTALL STEPS  (run on the shakemap machine via SSH)
════════════════════════════════════════════════════════════════

1. Install inotify-tools (if not already installed):
   sudo apt install inotify-tools

2. Install the systemd service:
   sudo mv /tmp/psa5-watcher.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable psa5-watcher
   sudo systemctl start psa5-watcher

3. Verify the watcher is running:
   sudo systemctl status psa5-watcher
   journalctl -u psa5-watcher -f

4. Add daily cron (runs at 01:00 WIB):
   (crontab -l 2>/dev/null; echo "0 1 * * * /home/sysop/scripts/psa5_daily.sh >> /home/sysop/scripts/psa5_daily.log 2>&1") | crontab -

5. Test send manually (pick any event directory):
   ls /home/sysop/seiscomp3/waveforms/ | head -3
   bash /home/sysop/scripts/psa5_send.sh /home/sysop/seiscomp3/waveforms/<EVENT_DIR>

6. Run a one-time full backfill (last 30 days):
   bash /home/sysop/scripts/psa5_daily.sh --days 30

   Or all historical events:
   bash /home/sysop/scripts/psa5_daily.sh --all

════════════════════════════════════════════════════════════════
EOF
