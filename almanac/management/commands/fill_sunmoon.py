# almanac/management/commands/fill_sunmoon.py
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.conf import settings
from almanac.models import SunMoonEvent
from skyfield.api import load, wgs84
from skyfield.almanac import find_discrete, risings_and_settings, phase_angle
import pytz

class Command(BaseCommand):
    help = "Compute Sun & Moon rise/set for all cities (except Jayapura) and store in DB"

    def handle(self, *args, **options):
        # Date span
        START_DATE = date(2025, 9, 6)
        END_DATE   = date(2037, 12, 31)

        ts   = load.timescale()
        eph  = load("de421.bsp")
        sun  = eph["sun"]
        moon = eph["moon"]

        total_rows = 0

        # Loop over cities, skip Jayapura
        for city in settings.SUNMOON_CITIES:
            name, lat, lon = city["name"], city["lat"], city["lon"]
            if name == "Jayapura":
                self.stdout.write(f"Skipping {name} (already processed)")
                continue

            tz = pytz.timezone("Asia/Jayapura")  # All Papua/West Papua are UTC+9
            observer = wgs84.latlon(lat, lon)

            rows = []
            current = START_DATE
            while current <= END_DATE:
                # midnight to midnight next day in UTC
                t0 = ts.utc(current.year, current.month, current.day, 0)
                t1 = ts.utc(current.year, current.month, current.day + 1, 0)

                # Sun rise/set
                sun_f = risings_and_settings(eph, sun, observer)
                times_sun, events_sun = find_discrete(t0, t1, sun_f)
                sun_rise, sun_set = None, None
                for t, e in zip(times_sun, events_sun):
                    dt_local = t.utc_datetime().astimezone(tz)
                    if e == 1:
                        sun_rise = dt_local
                    else:
                        sun_set = dt_local

                # Moon rise/set
                moon_f = risings_and_settings(eph, moon, observer)
                times_moon, events_moon = find_discrete(t0, t1, moon_f)
                moon_rise, moon_set = None, None
                for t, e in zip(times_moon, events_moon):
                    dt_local = t.utc_datetime().astimezone(tz)
                    if e == 1:
                        moon_rise = dt_local
                    else:
                        moon_set = dt_local

                # Moon phase at midnight (approx)
                ang   = phase_angle(eph, "moon", t0)
                phase = ang.degrees / 180.0  # 0 new -> 1 full

                rows.append(
                    SunMoonEvent(
                        date=current,
                        city=name,
                        sun_rise=sun_rise,
                        sun_set=sun_set,
                        moon_rise=moon_rise,
                        moon_set=moon_set,
                        moon_phase=phase,
                    )
                )
                current += timedelta(days=1)

            SunMoonEvent.objects.bulk_create(rows, ignore_conflicts=True)
            total_rows += len(rows)
            self.stdout.write(self.style.SUCCESS(f"{name}: inserted {len(rows)} rows"))

        self.stdout.write(self.style.SUCCESS(f"Done. Inserted {total_rows} total rows."))
