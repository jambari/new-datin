"""Siapa yang bertugas pada suatu waktu menurut jadwal dinas (jadwal.JadwalHarian).

Rentang dinas dihitung dari jam_mulai + durasi, bukan dari jam_selesai: pola PSM
(07:30, 24,5 jam) berakhir 08:00 HARI BERIKUTNYA walaupun jam_selesai > jam_mulai.
Status DL/Cuti/Sakit/Izin/TB (keterangan_lain) tidak dihitung bertugas.
"""
import datetime
import re

from .models import JadwalHarian, Pegawai

NOT_ON_DUTY = {"DL", "CUTI", "SAKIT", "IZIN", "TB"}


def _shift_window(tanggal, pola):
    start = datetime.datetime.combine(tanggal, pola.jam_mulai)
    return start, start + datetime.timedelta(hours=pola.durasi or 0)


def staff_on_duty_at(times):
    """{waktu lokal (naive): [Pegawai, ...]} untuk tiap waktu, dengan satu query.

    Waktu dalam jam setempat (WIT) tanpa zona. Dinas yang dimulai sampai 2 hari
    sebelumnya ikut diperiksa (cukup untuk dinas 24,5 jam).
    """
    times = list(times)
    if not times:
        return {}
    dates = {t.date() - datetime.timedelta(days=k) for t in times for k in (0, 1, 2)}
    rows = list(
        JadwalHarian.objects.filter(tanggal__in=dates, pola__isnull=False, pola__is_libur=False)
        .select_related("pegawai", "pola").order_by("pegawai__urutan", "pegawai__nama")
    )
    out = {}
    for t in times:
        staff = []
        for j in rows:
            if (j.keterangan_lain or "").upper() in NOT_ON_DUTY:
                continue
            start, end = _shift_window(j.tanggal, j.pola)
            if start <= t <= end and j.pegawai not in staff:
                staff.append(j.pegawai)
        out[t] = staff
    return out


def match_pegawai(text, pegawai_list):
    """Pegawai untuk teks nama bebas ('Juan', 'alif', 'RICHARD MILHOUS ..., S.Tr.Geof'), atau None."""
    raw = (text or "").strip()
    if not raw or raw.lower() == "staff ops":
        return None
    low = raw.lower()
    for p in pegawai_list:
        if low == p.nama.lower() or (p.user_id and low == p.user.username.lower()):
            return p
    words = [w for w in re.split(r"[\s.,]+", low.split(",")[0]) if len(w) >= 3]
    hits = []
    for p in pegawai_list:
        tokens = {w for w in re.split(r"[\s.,]+", p.nama.lower().split(",")[0]) if len(w) >= 3}
        if p.user_id:
            tokens.add(p.user.username.lower())
        if words and words[0] in tokens:
            hits.append(p)
    return hits[0] if len(hits) == 1 else None


def all_pegawai():
    return list(Pegawai.objects.select_related("user"))
