"""
LEMI-018 + Proton Monitor
Runs on the Windows PC that has both LEMI-018 and Proton software.

Checks every 60 s whether each process is running and responding,
then POSTs the status to the Django server.

Requirements (install once):
    pip install requests pywin32 psutil

Setup:
    1. Edit the CONFIG section below.
    2. Copy this file to C:\\lemi_monitor\\lemi_proton_monitor.py
    3. Run setup_lemi_task.ps1 as Administrator (change ScriptPath inside it).
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

LEMI_PROC_NAMES   = ["LEMI018.exe", "lemi018.exe", "LEMI.exe", "lemi.exe"]
PROTON_PROC_NAMES = ["Proton.exe", "proton.exe", "MagProton.exe"]  # adjust to actual exe name

POLL_SECONDS = 60
# ─────────────────────────────────────────────────────────────────────────────

COMPUTER_NAME = socket.gethostname()


def _is_process_running(proc_names: list[str]) -> bool:
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] in proc_names:
            return True
    return False


def _pids_for(proc_names: list[str]) -> set[int]:
    pids = set()
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'] in proc_names:
            pids.add(proc.info['pid'])
    return pids


def _visible_hwnds_for_pids(pids: set[int]) -> list[int]:
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


def _any_hung(hwnds: list[int]) -> bool:
    return any(ctypes.windll.user32.IsHungAppWindow(h) for h in hwnds)


def check_instrument(proc_names: list[str]) -> str:
    try:
        if not _is_process_running(proc_names):
            return "not_running"
        pids  = _pids_for(proc_names)
        hwnds = _visible_hwnds_for_pids(pids)
        if hwnds and _any_hung(hwnds):
            return "not_responding"
        return "ok"
    except Exception as exc:
        print(f"[monitor] check error: {exc}", file=sys.stderr)
        return "ok"


def report(instrument: str, status: str) -> None:
    payload = {
        "instrument":    instrument,
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
        print(f"[monitor] {instrument}={status} → HTTP {resp.status_code}")
    except requests.exceptions.RequestException as exc:
        print(f"[monitor] report failed ({instrument}): {exc}", file=sys.stderr)


def main() -> None:
    print(f"[lemi_proton_monitor] started on {COMPUTER_NAME}, poll every {POLL_SECONDS}s")
    while True:
        report("lemi",  check_instrument(LEMI_PROC_NAMES))
        report("proton", check_instrument(PROTON_PROC_NAMES))
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
