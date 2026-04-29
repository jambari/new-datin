"""
LEMI-018 Monitor — runs on the Windows PC that runs LEMI-018.

Checks every 60 seconds whether LEMI-018 is running and responding.
Posts status to the Django server. Django pushes a Telegram alert and
shows a dashboard popup when LEMI goes not-responding.

Requirements (install once on the Windows machine):
    pip install requests pywin32

Configuration — edit the three constants below, then set up Task Scheduler
to run this script at startup (see setup_lemi_task.ps1).
"""

import ctypes
import json
import socket
import sys
import time

import requests
import win32gui

# ── Configuration ─────────────────────────────────────────────────────────────
DJANGO_API_URL  = "http://36.91.166.189/magnet/api/lemi/status/"
BEARER_TOKEN    = "GANTI_DENGAN_LEMI_MONITOR_TOKEN_ANDA"   # must match LEMI_MONITOR_TOKEN in .env
LEMI_PROC_NAMES = ["LEMI018.exe", "lemi018.exe", "LEMI.exe", "lemi.exe"]  # adjust if different
POLL_SECONDS    = 60
# ─────────────────────────────────────────────────────────────────────────────

COMPUTER_NAME = socket.gethostname()


def _is_hung(hwnd: int) -> bool:
    """Return True if the window handle is 'Not Responding'."""
    # IsHungAppWindow returns non-zero when window is hung
    return bool(ctypes.windll.user32.IsHungAppWindow(hwnd))


def _find_lemi_windows() -> list[int]:
    """Return all top-level window handles belonging to LEMI processes."""
    import win32process
    import psutil

    lemi_pids: set[int] = set()
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'] in LEMI_PROC_NAMES:
            lemi_pids.add(proc.info['pid'])

    hwnds: list[int] = []

    def _cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid in lemi_pids:
                hwnds.append(hwnd)
        except Exception:
            pass

    win32gui.EnumWindows(_cb, None)
    return hwnds


def _is_process_running() -> bool:
    import psutil
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] in LEMI_PROC_NAMES:
            return True
    return False


def check_lemi() -> str:
    """Return 'ok', 'not_responding', or 'not_running'."""
    try:
        if not _is_process_running():
            return "not_running"

        hwnds = _find_lemi_windows()
        if not hwnds:
            # Process alive but no visible window yet — treat as ok
            return "ok"

        # If ANY main window is hung, report not_responding
        for hwnd in hwnds:
            if _is_hung(hwnd):
                return "not_responding"

        return "ok"

    except Exception as exc:
        print(f"[lemi_monitor] check error: {exc}", file=sys.stderr)
        return "ok"   # don't false-alarm on monitoring errors


def report_status(status: str) -> None:
    payload = {"status": status, "computer_name": COMPUTER_NAME}
    try:
        resp = requests.post(
            DJANGO_API_URL,
            data=json.dumps(payload),
            headers={
                "Authorization": f"Bearer {BEARER_TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        print(f"[lemi_monitor] {status} → HTTP {resp.status_code}")
    except requests.exceptions.RequestException as exc:
        print(f"[lemi_monitor] report failed: {exc}", file=sys.stderr)


def main() -> None:
    print(f"[lemi_monitor] started on {COMPUTER_NAME}, polling every {POLL_SECONDS}s")
    while True:
        status = check_lemi()
        report_status(status)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
