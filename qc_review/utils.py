"""
Utility: associate a QC event's origin_time with the jadwal dinas (shift roster).

The jadwal lives in Asia/Jayapura (WIT = UTC+9). Each JadwalHarian row ties a
Pegawai to a PolaDinas on a calendar date.  Two shift categories need special
treatment:

  Normal shift  (jam_selesai >= jam_mulai):  wholly within one calendar day.
  Overnight shift (jam_selesai < jam_mulai): starts on date D, ends on date D+1.
    Examples: MT 19:30→08:00, PSM 07:30→08:00 (durasi 24.5 h).

Algorithm:
  - Convert event origin_time (UTC) → WIT → (event_date, event_time).
  - For schedules on event_date:
      normal   → match if jam_mulai ≤ event_time ≤ jam_selesai
      overnight → match if event_time ≥ jam_mulai
  - For schedules on event_date − 1 day:
      overnight only → match if event_time ≤ jam_selesai
      (the shift started yesterday and is still running into today)
"""

from __future__ import annotations

import zoneinfo
from datetime import datetime, timedelta, timezone

WIT = zoneinfo.ZoneInfo("Asia/Jayapura")

# Event dengan origin_time sebelum 1 Juni 2026 WIT dianggap ON TIME
# (data backfill lama yang selisih insert-nya tidak relevan).
DELTA_ON_TIME_CUTOFF = datetime(2026, 6, 1, tzinfo=WIT)


def delta_on_time_info(origin_time, insert_time):
    """Kembalikan (delta_minutes, label).

    Aturan:
      - origin_time < 1 Juni 2026 WIT  -> (None, "ON TIME")
      - selisih insert <= 5 menit      -> (menit, "ON TIME")
      - selisih insert >  5 menit      -> (menit, "LATE")
    """
    if origin_time is None or insert_time is None:
        return None, "–"
    ot = origin_time
    it = insert_time
    if ot.tzinfo is None:
        ot = ot.replace(tzinfo=timezone.utc)
    if it.tzinfo is None:
        it = it.replace(tzinfo=timezone.utc)
    if ot < DELTA_ON_TIME_CUTOFF:
        return None, "ON TIME"
    minutes = (it - ot).total_seconds() / 60.0
    return round(minutes, 1), ("ON TIME" if minutes <= 5 else "LATE")


def _local(origin_time_utc):
    return origin_time_utc.astimezone(WIT).replace(tzinfo=None)


def _rows_for(entries):
    return [_row(j, j.tanggal, end.date() > start.date()) for j, start, end in entries]


def get_on_duty_staff(origin_time_utc) -> list[dict]:
    """
    Return a list of dicts describing who was on duty at origin_time_utc.

    Memakai aturan jadwal.duty (dinas lintas tengah malam & PSM, R s.d. 16:00, jam
    irisan serah terima dikreditkan ke dinas sebelumnya).

    Each dict:
        pegawai     : Pegawai instance
        pola        : PolaDinas instance
        shift_date  : date (the date the shift started, i.e. JadwalHarian.tanggal)
        overnight   : bool – True when the shift spans midnight
    """
    from jadwal.duty import duty_entries_at

    if origin_time_utc is None:
        return []
    t = _local(origin_time_utc)
    return _rows_for(duty_entries_at([t])[t])


def on_duty_resolver(origin_times):
    """Seperti get_on_duty_staff, untuk banyak kejadian sekaligus: jadwal diambil
    dalam satu query, lalu fungsi yang dikembalikan menjawab per origin_time."""
    from jadwal.duty import duty_entries_at

    by_time = duty_entries_at({_local(t) for t in origin_times if t is not None})

    def resolve(origin_time_utc):
        if origin_time_utc is None:
            return []
        return _rows_for(by_time.get(_local(origin_time_utc), []))

    return resolve


def _row(schedule, shift_date, overnight):
    return {
        "pegawai":    schedule.pegawai,
        "pola":       schedule.pola,
        "shift_date": shift_date,
        "overnight":  overnight,
    }
