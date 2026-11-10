"""Ambil keluaran ShakeMap dari .50 hanya untuk gempa dirasakan.

.189 tidak bisa membuka koneksi ke .50 secara langsung; jalurnya terowongan SSH balik
(`ssh host50`, lihat ~/.ssh/config di .189). Satu panggilan `find` mendaftar semua run ShakeMap
(nama folder + waktu ubah grid.xml); grid.xml dan stationlist.xml baru diunduh dengan rsync bila
run itu cocok dengan gempa dirasakan dan belum tersimpan.

Nama folder run: <WIB 14 digit>_<M*10>_<lintang*1000>_<bujur*1000>_<WIB>[_composite]
"""
import datetime
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

WIB = datetime.timezone(datetime.timedelta(hours=7))
_RUN = re.compile(r"^(?P<wib>\d{14})_(?P<mag>\d+)_(?P<lat>-?\d+)_(?P<lon>-?\d+)_\d{14}(?:_\w+)?$")
MATCH_SECONDS = 90
MATCH_DEG = 1.0


def _host():
    return getattr(settings, "ISOSEISMAL_SHAKEMAP_HOST", "host50")


def _root():
    return getattr(settings, "ISOSEISMAL_SHAKEMAP_DIR", "/home/sysop/shakemap/data_MMI")


@dataclass(frozen=True)
class Run:
    name: str            # nama folder di data_MMI
    wib_id: str          # WIB 14 digit
    time: datetime.datetime  # UTC
    lat: float
    lon: float
    mtime: float         # waktu ubah output/grid.xml (epoch)


def parse_listing(text):
    """[Run] dari keluaran `find … -printf '%h %T@\\n'` (baris: <dir>/output <mtime>)."""
    runs = []
    for line in text.splitlines():
        parts = line.strip().rsplit(" ", 1)
        if len(parts) != 2:
            continue
        name = Path(parts[0]).parent.name
        m = _RUN.match(name)
        if not m:
            continue
        try:
            t = datetime.datetime.strptime(m.group("wib"), "%Y%m%d%H%M%S").replace(tzinfo=WIB)
            mtime = float(parts[1])
        except ValueError:
            continue
        runs.append(Run(name, m.group("wib"), t.astimezone(datetime.timezone.utc),
                        int(m.group("lat")) / 1000, int(m.group("lon")) / 1000, mtime))
    return runs


def _ssh(command, timeout=60):
    return subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", _host(), command],
                          capture_output=True, text=True, timeout=timeout, check=True).stdout


def list_runs():
    """Semua run ShakeMap di .50 yang punya output/grid.xml."""
    out = _ssh(f"find {_root()} -mindepth 3 -maxdepth 3 -path '*/output/grid.xml' -printf '%h %T@\\n'")
    return parse_listing(out)


def best_run(runs, event_time, lat, lon):
    """Run terbaru (grid.xml paling baru) yang cocok waktu (±MATCH_SECONDS) dan posisi (≤ MATCH_DEG)."""
    cands = [r for r in runs
             if abs((r.time - event_time).total_seconds()) <= MATCH_SECONDS
             and abs(r.lat - lat) <= MATCH_DEG and abs(r.lon - lon) <= MATCH_DEG]
    return max(cands, key=lambda r: r.mtime) if cands else None


def fetch(run, dest):
    """Unduh grid.xml & stationlist.xml run itu ke folder dest; kembalikan (grid, stationlist|None)."""
    dest = Path(dest)
    src = f"{_host()}:{_root()}/{run.name}/output/"
    subprocess.run(["rsync", "-az", "-e", "ssh -o BatchMode=yes -o ConnectTimeout=15",
                    "--include=grid.xml", "--include=stationlist.xml", "--exclude=*", src, str(dest) + "/"],
                   capture_output=True, text=True, timeout=300, check=True)
    grid, stations = dest / "grid.xml", dest / "stationlist.xml"
    if not grid.exists():
        raise FileNotFoundError(f"{run.name}: grid.xml tidak terunduh")
    return grid, stations if stations.exists() else None


def temp_dir():
    return tempfile.TemporaryDirectory(prefix="isoseismal-")
