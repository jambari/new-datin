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
from datetime import timedelta

WIT = zoneinfo.ZoneInfo("Asia/Jayapura")


def get_on_duty_staff(origin_time_utc) -> list[dict]:
    """
    Return a list of dicts describing who was on duty at origin_time_utc.

    Each dict:
        pegawai     : Pegawai instance
        pola        : PolaDinas instance
        shift_date  : date (the date the shift started, i.e. JadwalHarian.tanggal)
        overnight   : bool – True when the shift spans midnight
    """
    from jadwal.models import JadwalHarian

    if origin_time_utc is None:
        return []

    event_wit  = origin_time_utc.astimezone(WIT)
    event_date = event_wit.date()
    event_time = event_wit.time()

    results = []

    for delta, check_date in ((0, event_date), (-1, event_date - timedelta(days=1))):
        schedules = (
            JadwalHarian.objects
            .filter(tanggal=check_date, pola__isnull=False, pola__is_libur=False)
            .select_related("pegawai", "pola")
            .order_by("pola__jam_mulai", "pegawai__urutan")
        )
        for s in schedules:
            start = s.pola.jam_mulai
            end   = s.pola.jam_selesai
            overnight = end < start  # jam_selesai wraps past midnight

            if delta == 0:
                # Shift started TODAY
                if not overnight:
                    if start <= event_time <= end:
                        results.append(_row(s, check_date, overnight))
                else:
                    if event_time >= start:
                        results.append(_row(s, check_date, overnight))
            else:
                # Shift started YESTERDAY — only counts if overnight and still running
                if overnight and event_time <= end:
                    results.append(_row(s, check_date, overnight))

    return results


def _row(schedule, shift_date, overnight):
    return {
        "pegawai":    schedule.pegawai,
        "pola":       schedule.pola,
        "shift_date": shift_date,
        "overnight":  overnight,
    }
