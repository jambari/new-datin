"""Baca rekaman kartu CF logger LEMI-018 (L018_*.B81) untuk mengisi celah data PC.

LEMI-018 berjalan mode Flash+PC: saat program di PC macet, logger tetap menulis ke kartu.
Tiap sektor 512 byte: header 32 byte ('LEMI018', byte seri, waktu BCD YY MM DD hh mm ss = waktu
rekaman pertama) lalu 30 rekaman 16 byte: X, Y, Z int32 (0,001 nT), suhu sensor & elektronik
int16 (0,01 C). Format diperiksa dengan membandingkan satu hari penuh terhadap berkas teks PC:
selisih terbesar 0,008 nT.
"""
import datetime
from pathlib import Path

import numpy as np

SECTOR = 512
HEADER = 32
MAGIC = b'LEMI018'
RECORDS = np.dtype([('x', '<i4'), ('y', '<i4'), ('z', '<i4'), ('t1', '<i2'), ('t2', '<i2')])
FIELD_LIMIT = 100000 * 1000     # |komponen| > 100.000 nT berarti sektor rusak


def _bcd(b):
    return (b >> 4) * 10 + (b & 0x0F)


def read_flash(path):
    """Urai satu berkas .B81 menjadi {tanggal: {detik dalam hari: (x, y, z, t1, t2)}}."""
    raw = Path(path).read_bytes()
    days = {}
    for s in range(len(raw) // SECTOR):
        sector = raw[s * SECTOR:(s + 1) * SECTOR]
        if not sector.startswith(MAGIC):
            continue
        try:
            start = datetime.datetime(2000 + _bcd(sector[8]), _bcd(sector[9]), _bcd(sector[10]),
                                      _bcd(sector[11]), _bcd(sector[12]), _bcd(sector[13]))
        except ValueError:
            continue
        if start.year < 2015:          # logger belum dapat waktu GPS (jam kembali ke 2000)
            continue
        for i, r in enumerate(np.frombuffer(sector[HEADER:], dtype=RECORDS)):
            if max(abs(int(r['x'])), abs(int(r['y'])), abs(int(r['z']))) > FIELD_LIMIT:
                continue
            t = start + datetime.timedelta(seconds=i)
            second = t.hour * 3600 + t.minute * 60 + t.second
            days.setdefault(t.date(), {})[second] = (r['x'] / 1000, r['y'] / 1000, r['z'] / 1000,
                                                     r['t1'] / 100, r['t2'] / 100)
    return days


def seconds_on_file(raw_dir, day):
    """Detik UTC tanggal `day` yang sudah ada di berkas teks."""
    from .kindex_fmi import raw_files_for, read_lemi_raw

    start = (day.toordinal() - datetime.date(1970, 1, 1).toordinal()) * 86400
    seen = set()
    for path in raw_files_for(raw_dir, day):
        t, _, _ = read_lemi_raw(path)
        seen.update(int(v) - start for v in t)
    return seen


def fill_day(raw_dir, day, records, dry_run=False):
    """Tulis detik yang belum ada ke berkas teks baru berformat LEMI. Kembalikan jumlah detik.

    Berkas lama tidak disentuh dan menjalankan ulang tidak menambah apa-apa.
    """
    missing = sorted(set(records) - seconds_on_file(raw_dir, day))
    if not missing or dry_run:
        return len(missing)
    def stamp(sec):
        return f'{day:%Y %m %d} {sec // 3600:02d} {sec % 3600 // 60:02d} {sec % 60:02d}'
    path = Path(raw_dir) / f'{stamp(missing[0])}.txt'
    lines = []
    for sec in missing:
        x, y, z, t1, t2 = records[sec]
        lines.append(f'{stamp(sec)} {x:9.2f} {y:9.2f} {z:9.2f} {t1:6.2f} {t2:6.2f} F N FL   0\n')
    path.write_text(''.join(lines))
    return len(missing)
