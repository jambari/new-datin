"""Siapa yang bertugas pada suatu waktu menurut jadwal dinas (jadwal.JadwalHarian).

Rentang dinas: jam_mulai s.d. jam_selesai, digeser ke hari berikutnya bila dinas
melewati tengah malam (MT 19:30–08:00) atau durasinya ±24 jam (PSM 07:30, 24,5 jam,
berakhir 08:00 HARI BERIKUTNYA walaupun jam_selesai > jam_mulai).
Status DL/Cuti/Sakit/Izin/TB (keterangan_lain) tidak dihitung bertugas.

Jam irisan serah terima: bila dua dinas sama-sama aktif, kejadian dikreditkan ke dinas
SEBELUMNYA (yang mulai lebih awal dan berakhir lebih awal) — mis. 07:30–08:00 ke dinas
malam, 19:30–20:00 ke dinas PS. Dinas yang mulai bersamaan (PS & R) dihitung bersama.
"""
import datetime
import re

from .models import JadwalHarian, Pegawai

NOT_ON_DUTY = {"DL", "CUTI", "SAKIT", "IZIN", "TB"}


def _shift_window(tanggal, pola):
    start = datetime.datetime.combine(tanggal, pola.jam_mulai)
    end = datetime.datetime.combine(tanggal, pola.jam_selesai)
    hours = pola.durasi or 0
    while end <= start or (end - start) < datetime.timedelta(hours=hours - 1):
        end += datetime.timedelta(days=1)
    return start, end


def duty_entries_at(times):
    """{waktu lokal (naive): [(JadwalHarian, mulai, selesai), ...]} yang bertugas, satu query.

    Waktu dalam jam setempat (WIT) tanpa zona. Dinas yang dimulai sampai 2 hari
    sebelumnya ikut diperiksa (cukup untuk dinas 24,5 jam). Aturan serah terima
    diterapkan (lihat docstring modul).
    """
    times = list(times)
    if not times:
        return {}
    dates = {t.date() - datetime.timedelta(days=k) for t in times for k in (0, 1, 2)}
    rows = list(
        JadwalHarian.objects.filter(tanggal__in=dates, pola__isnull=False, pola__is_libur=False)
        .select_related("pegawai", "pola").order_by("pola__jam_mulai", "pegawai__urutan", "pegawai__nama")
    )
    windows = [(j, *_shift_window(j.tanggal, j.pola)) for j in rows
               if (j.keterangan_lain or "").upper() not in NOT_ON_DUTY]
    out = {}
    for t in times:
        covering = [(j, start, end) for j, start, end in windows if start <= t <= end]
        # Serah terima: dinas yang baru masuk belum dihitung selama dinas sebelumnya
        # (mulai & selesai lebih awal) masih berjalan.
        kept, seen = [], set()
        for j, start, end in covering:
            if any(s2 < start and e2 < end for _j, s2, e2 in covering):
                continue
            if j.pegawai_id not in seen:
                seen.add(j.pegawai_id)
                kept.append((j, start, end))
        out[t] = kept
    return out


def staff_on_duty_at(times):
    """{waktu lokal (naive): [Pegawai, ...]} untuk tiap waktu, dengan satu query."""
    return {t: [j.pegawai for j, _s, _e in entries] for t, entries in duty_entries_at(times).items()}


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
