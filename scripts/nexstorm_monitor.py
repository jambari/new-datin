"""
Nexstorm Monitor
Runs on the Windows PC that has the Nexstorm lightning-detection software.

Checks every 60 s whether Nexstorm is running and responding,
then POSTs the status to the Django server.

Requirements (install once):
    pip install requests pywin32 psutil

Setup:
    1. Edit the CONFIG section below.
    2. Copy this file to C:\\nexstorm_monitor\\nexstorm_monitor.py
    3. Run setup_lemi_task.ps1 as Administrator
       (change ScriptPath to C:\\nexstorm_monitor\\nexstorm_monitor.py).
"""

import ctypes
import json
import socket
import sys
import time

import psutil
import requests
import win32gui
import win32process

# ── CONFIG ────────────────────────────────────────────────────────────────────
DJANGO_API_URL = "http://36.91.166.189/magnet/api/instrument/status/"
BEARER_TOKEN   = "GANTI_DENGAN_LEMI_MONITOR_TOKEN_ANDA"   # same as LEMI_MONITOR_TOKEN in .env

NEXSTORM_PROC_NAMES = ["Nexstorm.exe", "nexstorm.exe", "NexStorm.exe"]  # adjust if needed

POLL_SECONDS = 60
# ─────────────────────────────────────────────────────────────────────────────

COMPUTER_NAME = socket.gethostname()


def _is_process_running() -> bool:
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] in NEXSTORM_PROC_NAMES:
            return True
    return False


def _pids() -> set[int]:
    pids = set()
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'] in NEXSTORM_PROC_NAMES:
            pids.add(proc.info['pid'])
    return pids


def _visible_hwnds(pids: set[int]) -> list[int]:
    hwnds = []
    def _cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid in pids:
                hwnds.append(hwnd)
        except Exception:
            pass
    win32gui.EnumWindows(_cb, None)
    return hwnds


def check_nexstorm() -> str:
    try:
        if not _is_process_running():
            return "not_running"
        pids  = _pids()
        hwnds = _visible_hwnds(pids)
        if hwnds and any(ctypes.windll.user32.IsHungAppWindow(h) for h in hwnds):
            return "not_responding"
        return "ok"
    except Exception as exc:
        print(f"[nexstorm_monitor] check error: {exc}", file=sys.stderr)
        return "ok"


def report(status: str) -> None:
    payload = {
        "instrument":    "nexstorm",
        "status":        status,
        "computer_name": COMPUTER_NAME,
    }
    try:
        resp = requests.post(
            DJANGO_API_URL,
            data=json.dumps(payload),
            headers={
                "Authorization": f"Bearer {BEARER_TOKEN}",
                "Content-Type":  "application/json",
            },
            timeout=10,
        )
        print(f"[nexstorm_monitor] {status} → HTTP {resp.status_code}")
    except requests.exceptions.RequestException as exc:
        print(f"[nexstorm_monitor] report failed: {exc}", file=sys.stderr)


def main() -> None:
    print(f"[nexstorm_monitor] started on {COMPUTER_NAME}, poll every {POLL_SECONDS}s")
    while True:
        report(check_nexstorm())
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
