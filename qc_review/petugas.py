"""Lekatkan petugas jaga (menurut jadwal dinas) ke event QC."""
import datetime

from jadwal.duty import staff_on_duty_at

from .utils import WIT

PETUGAS_START = datetime.datetime(2026, 1, 1, tzinfo=WIT)   # jadwal dinas tersedia & dipakai sejak 2026


def local_time(origin_time):
    """Waktu kejadian dalam WIT tanpa zona (format jadwal dinas)."""
    return origin_time.astimezone(WIT).replace(tzinfo=None)


def assign_petugas(events, refresh=False):
    """Isi Event.petugas untuk sekumpulan event (satu query jadwal). Kembalikan {event: [Pegawai]}."""
    events = [e for e in events if e.origin_time and e.origin_time >= PETUGAS_START]
    if not refresh:
        events = [e for e in events if not e.petugas.exists()]
    on_duty = staff_on_duty_at({local_time(e.origin_time) for e in events})
    result = {}
    for e in events:
        staff = on_duty.get(local_time(e.origin_time), [])
        e.petugas.set(staff)
        result[e] = staff
    return result
