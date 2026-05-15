#!/bin/bash
# Fetch today's earthquake events from QuakeLink (local only),
# then sync the full EventBrowser table to production.
#
# Run automatically via cron every 2 hours.
# Logs: /home/lenovo/new-datin/logs/fetch_and_sync.log

PROJ_DIR=/home/lenovo/new-datin
VENV_PY=$PROJ_DIR/venv/bin/python3
LOG=$PROJ_DIR/logs/fetch_and_sync.log
TMP_SQL=/tmp/eventbrowser_sync.sql

PROD_HOST=36.91.166.189
PROD_SSH_USER=sysop
PROD_SSH_PASS=sysop01

LOCAL_DB=datin
LOCAL_DB_USER=jambari
LOCAL_DB_PASS=Jay97696

PROD_DB=datin
PROD_DB_USER=jambari
PROD_DB_PASS=HIWQMk2LN7ON5H_LYqnuVrpNUoI

mkdir -p "$PROJ_DIR/logs"
exec >> "$LOG" 2>&1

echo ""
echo "===== $(date '+%Y-%m-%d %H:%M:%S') ====="

# 1. Fetch today's events from QuakeLink into local DB
echo "[1] Fetching from QuakeLink..."
cd "$PROJ_DIR"
$VENV_PY manage.py fetch_events --today
if [ $? -ne 0 ]; then
    echo "ERROR: fetch_events failed. Aborting sync."
    exit 1
fi

# 2. Dump the full EventBrowser table from local DB
echo "[2] Dumping local EventBrowser table..."
PGPASSWORD=$LOCAL_DB_PASS pg_dump \
    -h 127.0.0.1 \
    -U "$LOCAL_DB_USER" \
    -d "$LOCAL_DB" \
    -t repository_eventbrowser \
    --data-only \
    -f "$TMP_SQL"
if [ $? -ne 0 ]; then
    echo "ERROR: pg_dump failed. Aborting sync."
    exit 1
fi
echo "    Dump size: $(wc -l < $TMP_SQL) lines"

# 3. Copy dump to production and restore
echo "[3] Syncing to production ($PROD_HOST)..."
sshpass -p "$PROD_SSH_PASS" scp -o StrictHostKeyChecking=no \
    "$TMP_SQL" "${PROD_SSH_USER}@${PROD_HOST}:/tmp/eventbrowser_sync.sql"

sshpass -p "$PROD_SSH_PASS" ssh -o StrictHostKeyChecking=no \
    "${PROD_SSH_USER}@${PROD_HOST}" "
        PGPASSWORD='$PROD_DB_PASS' psql -h 127.0.0.1 -U '$PROD_DB_USER' -d '$PROD_DB' \
            -c 'TRUNCATE TABLE repository_eventbrowser RESTART IDENTITY;' && \
        PGPASSWORD='$PROD_DB_PASS' psql -h 127.0.0.1 -U '$PROD_DB_USER' -d '$PROD_DB' \
            -f /tmp/eventbrowser_sync.sql && \
        rm /tmp/eventbrowser_sync.sql && \
        echo 'Production sync OK'
    "

if [ $? -ne 0 ]; then
    echo "ERROR: Production sync failed."
    rm -f "$TMP_SQL"
    exit 1
fi

rm -f "$TMP_SQL"
echo "[Done] $(date '+%Y-%m-%d %H:%M:%S')"
