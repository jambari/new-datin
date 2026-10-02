"""Pembuat peta GMT — port dari skrip /home/jamz/<region>/buat_peta.sh di .188.

Di .188 alurnya: SeisComp -> insertgempa.php -> ingest_django.sh ->
`manage.py ingest_gempa <region>` -> insert event ke DB -> jalankan buat_peta.sh
(fire-and-forget). Di .189 tidak ada feed SeisComp, jadi modul ini yang jadi
pintu masuknya: dipakai oleh management command, task Celery, dan tombol di
admin.

Kontrak argumen (sama dengan .188):

    bash buat_peta.sh <lat> <lon> <mag> <tanggal> <HHMMSS> <depth>

dan hasilnya:

    <GMT_UPLOADS_DIR>/<PREFIX>_<tanggal>_<HHMMSS>UTC.png

dengan PREFIX: jay=JAY, balai=PGR5, nabire=NBPI, sorong=SWI — persis nama yang
dicari `admin.gmt_image()`.

Perbedaan dari .188: di sana skrip dijalankan `subprocess.Popen` tanpa ditunggu,
sehingga kegagalan tidak pernah terlihat. Di sini proses ditunggu (dengan
timeout) supaya hasilnya bisa dilaporkan — penting karena tombol admin
menampilkan pesan berhasil/gagal.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime

from django.conf import settings

#: region -> awalan nama berkas. Skrip tiap region ada di <GMT_ROOT>/<region>.
REGIONS = {
    'jay':    'JAY',
    'balai':  'PGR5',
    'nabire': 'NBPI',
    'sorong': 'SWI',
}

#: region -> model katalognya (dipakai command & signal).
REGION_MODEL = {
    'jay':    'Gempa',
    'balai':  'Balaigempa',
    'sorong': 'Gempasorong',
    'nabire': 'Gempanabire',
}

_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_ORIGIN_RE = re.compile(r'^\d{2}:?\d{2}:?\d{2}$')


class GmtError(Exception):
    """Argumen tidak valid / peta gagal dibuat."""


@dataclass
class GmtResult:
    created: bool = False
    skipped: bool = False
    path: str = ''
    filename: str = ''
    stdout: str = ''
    stderr: str = ''
    seconds: float = 0.0
    detail: str = field(default='', repr=True)


def _uploads_dir() -> str:
    return getattr(settings, 'GMT_UPLOADS_DIR', '/var/www/gmt/uploads')


def _workdir() -> str:
    return getattr(settings, 'GMT_WORKDIR', '/var/www/gmt/jay')


def script_path(region: str) -> str:
    region = (region or '').strip().lower()
    if region not in REGIONS:
        raise GmtError(f'Region tidak dikenal: {region!r}. Pilihan: {sorted(REGIONS)}')
    return os.path.join(os.path.dirname(_workdir()), region, 'buat_peta.sh')


def prefix_for(region: str) -> str:
    region = (region or '').strip().lower()
    if region not in REGIONS:
        raise GmtError(f'Region tidak dikenal: {region!r}')
    return REGIONS[region]


def normalise_origin(origin) -> str:
    """'21:37:17' / '213717' -> '213717' (HHMMSS)."""
    text = str(origin or '').strip()
    if not _ORIGIN_RE.match(text):
        raise GmtError(f'origin tidak valid: {origin!r} (harap HH:MM:SS)')
    return text.replace(':', '')


def map_filename(region: str, tanggal, origin) -> str:
    """Nama berkas yang dicari gmt_image(): PREFIX_tanggal_HHMMSSUTC.png."""
    tanggal_str = tanggal.isoformat() if isinstance(tanggal, (date, datetime)) else str(tanggal).strip()
    if not _DATE_RE.match(tanggal_str):
        raise GmtError(f'tanggal tidak valid: {tanggal!r} (harap YYYY-MM-DD)')
    return f'{prefix_for(region)}_{tanggal_str}_{normalise_origin(origin)}UTC.png'


def map_path(region: str, tanggal, origin) -> str:
    return os.path.join(_uploads_dir(), map_filename(region, tanggal, origin))


def map_exists(region: str, tanggal, origin) -> bool:
    return os.path.exists(map_path(region, tanggal, origin))


def _clean_number(value, name: str) -> str:
    """Terima angka/str, tolak apa pun yang bukan angka (argumen masuk ke shell)."""
    text = str(value).strip()
    try:
        float(text)
    except (TypeError, ValueError):
        raise GmtError(f'{name} tidak valid: {value!r}')
    if not re.match(r'^-?\d+(\.\d+)?$', text):
        raise GmtError(f'{name} tidak valid: {value!r}')
    return text


def generate(region: str, *, lat, lon, mag, tanggal, origin, depth,
             force: bool = False, timeout: int = None) -> GmtResult:
    """Jalankan buat_peta.sh untuk satu event.

    Idempoten: kalau berkasnya sudah ada dan force=False, skrip tidak dijalankan
    (ini yang menjaga agar sinkronisasi katalog tidak memicu ribuan render).
    """
    region = (region or '').strip().lower()
    if not getattr(settings, 'GMT_ENABLED', True):
        return GmtResult(skipped=True, detail='GMT dimatikan (GMT_ENABLED=False)')

    script = script_path(region)
    if not os.path.exists(script):
        raise GmtError(f'Skrip GMT tidak ada: {script}')

    target = map_path(region, tanggal, origin)
    if os.path.exists(target) and not force:
        return GmtResult(skipped=True, path=target,
                         filename=os.path.basename(target),
                         detail='peta sudah ada (pakai force=True untuk membuat ulang)')

    args = [
        _clean_number(lat, 'lintang'),
        _clean_number(lon, 'bujur'),
        _clean_number(mag, 'magnitudo'),
        (tanggal.isoformat() if isinstance(tanggal, (date, datetime)) else str(tanggal).strip()),
        normalise_origin(origin),
        _clean_number(depth, 'depth'),
    ]
    if not _DATE_RE.match(args[3]):
        raise GmtError(f'tanggal tidak valid: {tanggal!r}')

    os.makedirs(_uploads_dir(), exist_ok=True)

    env = dict(os.environ)
    env.update({
        'GMT_WORKDIR': _workdir(),
        'GMT_UPLOADS_DIR': _uploads_dir(),
        'GMT_HISTORI': os.path.join(os.path.dirname(_workdir()), region, 'histori_gmt.gmt'),
    })

    timeout = timeout or getattr(settings, 'GMT_TIMEOUT', 120)
    started = datetime.now()
    try:
        proc = subprocess.run(
            ['bash', script, *args],
            cwd=os.path.dirname(script),
            env=env, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise GmtError(f'GMT melebihi {timeout}s untuk {os.path.basename(target)}') from exc

    elapsed = (datetime.now() - started).total_seconds()
    result = GmtResult(path=target, filename=os.path.basename(target),
                       stdout=proc.stdout or '', stderr=proc.stderr or '',
                       seconds=elapsed)

    if proc.returncode != 0:
        raise GmtError(
            f'buat_peta.sh gagal (exit {proc.returncode}) untuk '
            f'{os.path.basename(target)}: {(proc.stderr or proc.stdout or "").strip()[:400]}'
        )
    if not os.path.exists(target):
        raise GmtError(
            f'buat_peta.sh selesai tanpa error tapi berkas tidak ada: {target}. '
            f'stderr: {(proc.stderr or "").strip()[:300]}'
        )

    result.created = True
    result.detail = f'{os.path.basename(target)} dibuat dalam {elapsed:.1f}s'
    return result
