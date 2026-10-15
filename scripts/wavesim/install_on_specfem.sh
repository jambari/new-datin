#!/usr/bin/env bash
# install_on_specfem.sh — install/update the wave-simulation worker on the SPECFEM host.
#
# Run ON 172.21.63.51 (user sysop) from a copy of this directory:
#   scp -r scripts/wavesim sysop@172.21.63.51:/tmp/wavesim_src
#   ssh sysop@172.21.63.51 'bash /tmp/wavesim_src/install_on_specfem.sh [TOKEN]'
#
# Needs SPECFEM3D built with CUDA in ~/specfem3d (plus xmeshfem3D) and the
# system python3 with numpy/scipy/matplotlib/Pillow/requests.
# TOKEN must equal WAVESIM_WORKER_TOKEN in new-datin's .env.production; it is
# only written when given (first install), otherwise worker.env is kept.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/wavesim"
MARK="# wavesim worker (new-datin gempa merusak)"
LINE="*/5 * * * * flock -n /tmp/wavesim.lock python3 $DEST/wavesim_worker.py >> $DEST/worker.log 2>&1 $MARK"

[[ -x "$HOME/specfem3d/bin/xspecfem3D" ]] || { echo "missing ~/specfem3d/bin/xspecfem3D" >&2; exit 1; }
python3 -c "import numpy, scipy, matplotlib, PIL, requests" || { echo "python3 modules missing" >&2; exit 1; }

mkdir -p "$DEST/runs"
for f in specfem_inputs.py postprocess.py wavesim_worker.py; do
  install -m 0644 "$SRC/$f" "$DEST/$f"
done
echo "installed worker into $DEST"

if [[ $# -ge 1 ]]; then
  umask 077
  printf 'WAVESIM_API=https://stageof-jayapura.bmkg.go.id/api/wavesim/\nWAVESIM_TOKEN=%s\n' "$1" > "$DEST/worker.env"
  echo "wrote $DEST/worker.env"
fi
[[ -r "$DEST/worker.env" ]] || { echo "no $DEST/worker.env yet — rerun with the token" >&2; exit 1; }

current="$(crontab -l 2>/dev/null | grep -vF "$MARK" || true)"
printf '%s\n%s\n' "$current" "$LINE" | sed '/^$/d' | crontab -
echo "crontab entry:"
crontab -l | grep -F "$MARK"
