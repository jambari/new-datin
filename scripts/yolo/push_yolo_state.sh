#!/usr/bin/env bash
# push_yolo_state.sh — Send a snapshot of YOLO training state to new-datin prod.
#
# Runs on the YOLO host (172.21.63.51) via cron every 5 minutes:
#   */5 * * * * /home/sysop/yolo-training/push_yolo_state.sh >> /home/sysop/yolo-training/push_yolo_state.log 2>&1

set -u

python3 - <<'PY'
import json, os, subprocess, sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

API_URL   = "http://36.91.166.189/api/yolo/state/"
API_TOKEN = "bfca5407ee75ff0a62ac121fb6ff1b1a1c3b348222996125958a5ccb1d0e46c1"
RUN_DIR   = "/home/sysop/yolo-training/runs/detect/runs/yolov11s_training"
WD_LOG    = "/home/sysop/yolo-training/thermal_watchdog.log"
TIMEOUT   = 30

def read_text(path, maxbytes=2_000_000, tail=None):
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", errors="replace") as f:
            data = f.read(maxbytes)
        if tail is not None:
            data = "\n".join(data.splitlines()[-tail:])
        return data
    except OSError:
        return ""

def read_gpu():
    try:
        out = subprocess.check_output(
            ["nvidia-smi",
             "--query-gpu=temperature.gpu,fan.speed,power.draw,utilization.gpu",
             "--format=csv,noheader,nounits"],
            timeout=10,
        ).decode().strip().splitlines()[0]
        t, f, p, u = [x.strip() for x in out.split(",")]
        return {
            "temp":  int(t)   if t   and t.isdigit() else None,
            "fan":   int(f)   if f   and f.isdigit() else None,
            "power": float(p) if p else None,
            "util":  int(u)   if u   and u.isdigit() else None,
        }
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, ValueError):
        return {"temp": None, "fan": None, "power": None, "util": None}

payload = {
    "results_csv":   read_text(os.path.join(RUN_DIR, "results.csv")),
    "watchdog_tail": read_text(WD_LOG, tail=30),
    "gpu":           read_gpu(),
    "pushed_at":     datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
}

body = json.dumps(payload).encode()
req = Request(
    API_URL, data=body, method="POST",
    headers={
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {API_TOKEN}",
    },
)

stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
gpu = payload["gpu"]
try:
    with urlopen(req, timeout=TIMEOUT) as resp:
        msg = resp.read().decode()[:200]
        print(f"[{stamp}] OK   bytes={len(body)} gpu={gpu['temp']}°C/{gpu['util']}%  {msg}")
except HTTPError as e:
    print(f"[{stamp}] HTTP={e.code} {e.read().decode()[:200]}", file=sys.stderr)
    sys.exit(1)
except URLError as e:
    print(f"[{stamp}] URLError {e.reason}", file=sys.stderr)
    sys.exit(1)
PY
