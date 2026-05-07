#!/bin/bash
set -e

APP_DIR="/var/www/html"
VENV="$APP_DIR/venv/bin"

# Re-exec after pull so bash always runs the latest version of this script
if [ "$1" != "--post-pull" ]; then
    echo "[1/6] Pulling latest code..."
    cd "$APP_DIR"
    git fetch origin main
    git reset --hard origin/main
    exec bash "$APP_DIR/scripts/deploy.sh" --post-pull
fi

echo "[2/6] Installing dependencies..."
$VENV/pip install -r $APP_DIR/requirements.txt --quiet 2>&1 | grep -v "^$" | grep -v "notice" || true

echo "[3/6] Running migrations..."
$VENV/python $APP_DIR/manage.py migrate --noinput

echo "[4/6] Collecting static files..."
$VENV/python $APP_DIR/manage.py collectstatic --noinput --clear -v 0

echo "[5/6] Restarting services..."
sudo systemctl restart datin.service
sudo systemctl restart datin-celery.service
sudo systemctl restart datin-celery-beat.service

echo "[6/6] Checking service status..."
sudo systemctl is-active datin.service
sudo systemctl is-active datin-celery.service
sudo systemctl is-active datin-celery-beat.service

echo ""
echo "Deploy complete."
