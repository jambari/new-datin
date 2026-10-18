# almanac/management/commands/fill_sunmoon.py
"""Hitung terbit/terbenam Matahari dan Bulan serta fase Bulan untuk semua kota SUNMOON_CITIES.

Satu baris SunMoonEvent = satu tanggal WIT (00:00–24:00 WIT = 15:00 UTC hari sebelumnya s.d.
15:00 UTC). Waktu disimpan dalam UTC dan ditampilkan dalam WIT. Terbit/terbenam mengikuti definisi
USNO (tepi atas piringan menyentuh horizon, refraksi 34′) bawaan Skyfield find_risings/find_settings.
moon_phase = elongasi ekliptika Bulan−Matahari / 360° pada pukul 12:00 WIT
(0 = bulan baru, 0,25 = kuartal pertama, 0,5 = purnama, 0,75 = kuartal ketiga).
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from skyfield import almanac
from skyfield.api import load, wgs84

from almanac.models import SunMoonEvent

WIT = timezone(timedelta(hours=9))
EPHEMERIS = settings.BASE_DIR / "de421.bsp"


class Command(BaseCommand):
    help = "Hitung terbit/terbenam Matahari & Bulan dan fase Bulan per tanggal WIT (simpan UTC)."

    def add_arguments(self, parser):
        parser.add_argument("--start", type=date.fromisoformat, default=date(2025, 9, 6))
        parser.add_argument("--end", type=date.fromisoformat, default=date(2037, 12, 31))
        parser.add_argument("--city", action="append", help="Hanya kota ini (boleh diulang)")

    def handle(self, *args, start, end, city, **options):
        ts = load.timescale()
        eph = load(str(EPHEMERIS))
        earth, sun, moon = eph["earth"], eph["sun"], eph["moon"]
        t0 = ts.from_datetime(datetime.combine(start, time.min, tzinfo=WIT))
        t1 = ts.from_datetime(datetime.combine(end + timedelta(days=1), time.min, tzinfo=WIT))
        ndays = (end - start).days + 1
        days = [start + timedelta(days=i) for i in range(ndays)]
        noon = ts.from_datetimes([datetime.combine(d, time(12), tzinfo=WIT) for d in days])
        phases = (almanac.moon_phase(eph, noon).degrees / 360.0).tolist()

        cities = [c for c in settings.SUNMOON_CITIES if not city or c["name"] in city]
        for c in cities:
            observer = earth + wgs84.latlon(c["lat"], c["lon"])
            events = defaultdict(dict)
            for key, finder, body in (("sun_rise", almanac.find_risings, sun), ("sun_set", almanac.find_settings, sun),
                                      ("moon_rise", almanac.find_risings, moon),
                                      ("moon_set", almanac.find_settings, moon)):
                times, crosses = finder(observer, body, t0, t1)
                for t, ok in zip(times, crosses):
                    if not ok:
                        continue
                    utc = t.utc_datetime().replace(microsecond=0)
                    events[utc.astimezone(WIT).date()].setdefault(key, utc)
            existing = {e.date: e for e in SunMoonEvent.objects.filter(city=c["name"], date__gte=start, date__lte=end)}
            update, create = [], []
            for d, phase in zip(days, phases):
                values = {"sun_rise": None, "sun_set": None, "moon_rise": None, "moon_set": None,
                          **events.get(d, {}), "moon_phase": phase}
                row = existing.get(d)
                if row is None:
                    create.append(SunMoonEvent(date=d, city=c["name"], **values))
                else:
                    for k, v in values.items():
                        setattr(row, k, v)
                    update.append(row)
            with transaction.atomic():
                SunMoonEvent.objects.bulk_update(update, ["sun_rise", "sun_set", "moon_rise", "moon_set", "moon_phase"],
                                                 batch_size=1000)
                SunMoonEvent.objects.bulk_create(create, batch_size=1000)
            self.stdout.write(self.style.SUCCESS(f"{c['name']}: {len(update)} diperbarui, {len(create)} baru"))
