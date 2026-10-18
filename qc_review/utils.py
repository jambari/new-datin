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


def _schedules_for(dates):
    """{tanggal: [JadwalHarian, ...]} (dinas, bukan libur) untuk sekumpulan tanggal, satu query."""
    from jadwal.models import JadwalHarian

    by_date = {d: [] for d in dates}
    qs = (
        JadwalHarian.objects
        .filter(tanggal__in=list(by_date), pola__isnull=False, pola__is_libur=False)
        .select_related("pegawai", "pola")
        .order_by("pola__jam_mulai", "pegawai__urutan")
    )
    for s in qs:
        by_date[s.tanggal].append(s)
    return by_date


def _on_duty(event_wit, by_date):
    event_date = event_wit.date()
    event_time = event_wit.time()
    results = []
    for delta, check_date in ((0, event_date), (-1, event_date - timedelta(days=1))):
        for s in by_date.get(check_date, ()):
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


def get_on_duty_staff(origin_time_utc) -> list[dict]:
    """
    Return a list of dicts describing who was on duty at origin_time_utc.

    Each dict:
        pegawai     : Pegawai instance
        pola        : PolaDinas instance
        shift_date  : date (the date the shift started, i.e. JadwalHarian.tanggal)
        overnight   : bool – True when the shift spans midnight
    """
    if origin_time_utc is None:
        return []
    event_wit = origin_time_utc.astimezone(WIT)
    d = event_wit.date()
    return _on_duty(event_wit, _schedules_for([d, d - timedelta(days=1)]))


def on_duty_resolver(origin_times):
    """Seperti get_on_duty_staff, untuk banyak kejadian sekaligus: jadwal diambil
    dalam satu query, lalu fungsi yang dikembalikan menjawab per origin_time."""
    dates = set()
    for t in origin_times:
        if t is not None:
            d = t.astimezone(WIT).date()
            dates.update((d, d - timedelta(days=1)))
    by_date = _schedules_for(dates)

    def resolve(origin_time_utc):
        if origin_time_utc is None:
            return []
        return _on_duty(origin_time_utc.astimezone(WIT), by_date)

    return resolve


def _row(schedule, shift_date, overnight):
    return {
        "pegawai":    schedule.pegawai,
        "pola":       schedule.pola,
        "shift_date": shift_date,
        "overnight":  overnight,
    }
