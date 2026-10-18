import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from .models import SunMoonEvent


def make_event(**kwargs):
    defaults = dict(
        date=datetime.date(2024, 3, 1),
        city='Jayapura',
        sun_rise=datetime.datetime(2024, 3, 1, 6, 0, tzinfo=datetime.timezone.utc),
        sun_set=datetime.datetime(2024, 3, 1, 18, 0, tzinfo=datetime.timezone.utc),
        moon_rise=datetime.datetime(2024, 3, 1, 7, 0, tzinfo=datetime.timezone.utc),
        moon_set=datetime.datetime(2024, 3, 1, 19, 0, tzinfo=datetime.timezone.utc),
        moon_phase=0.5,
    )
    defaults.update(kwargs)
    return SunMoonEvent.objects.create(**defaults)


class SunMoonEventModelTest(TestCase):
    def test_create(self):
        ev = make_event()
        self.assertEqual(ev.city, 'Jayapura')
        self.assertEqual(ev.moon_phase, 0.5)

    def test_unique_together_date_city(self):
        make_event(date=datetime.date(2024, 3, 1), city='Jayapura')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            make_event(date=datetime.date(2024, 3, 1), city='Jayapura')

    def test_different_city_same_date_allowed(self):
        make_event(date=datetime.date(2024, 3, 1), city='Jayapura')
        ev2 = make_event(date=datetime.date(2024, 3, 1), city='Serui')
        self.assertEqual(ev2.city, 'Serui')

    def test_ordering_by_date(self):
        make_event(date=datetime.date(2024, 3, 2), city='Jayapura')
        make_event(date=datetime.date(2024, 3, 1), city='Serui')
        dates = list(SunMoonEvent.objects.values_list('date', flat=True))
        self.assertEqual(dates[0], datetime.date(2024, 3, 1))


class AlmanacViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('testuser', password='pass123')
        self.client.login(username='testuser', password='pass123')
        make_event()

    def test_event_list_get(self):
        resp = self.client.get(reverse('event_list'))
        self.assertEqual(resp.status_code, 200)

    def test_event_list_filter_by_city(self):
        resp = self.client.get(reverse('event_list'), {'city': 'Jayapura'})
        self.assertEqual(resp.status_code, 200)

    def test_event_list_filter_by_date_range(self):
        resp = self.client.get(reverse('event_list'), {
            'start_date': '2024-01-01',
            'end_date': '2024-12-31',
        })
        self.assertEqual(resp.status_code, 200)

    def test_sunmoon_report_get(self):
        resp = self.client.get(reverse('sunmoon_report'))
        self.assertEqual(resp.status_code, 200)

    def test_sunmoon_report_with_month_year(self):
        resp = self.client.get(reverse('sunmoon_report'), {'month': 3, 'year': 2024})
        self.assertEqual(resp.status_code, 200)


class FillSunMoonCommandTest(TestCase):
    def test_rows_are_wit_days_stored_in_utc_with_correct_phase(self):
        from django.core.management import call_command
        from almanac.templatetags.almanac_extras import fase_bulan
        wit = datetime.timezone(datetime.timedelta(hours=9))
        make_event(date=datetime.date(2026, 1, 15), moon_phase=0.04)        # baris lama diperbarui
        call_command("fill_sunmoon", "--start=2026-01-01", "--end=2026-01-31", "--city=Jayapura",
                     stdout=open("/dev/null", "w"))
        rows = {e.date: e for e in SunMoonEvent.objects.filter(city="Jayapura")}
        self.assertEqual(len(rows), 31)                                     # baris 15/1 diperbarui, bukan diduplikasi
        for d, e in rows.items():
            if d.year != 2026:
                continue
            for t in (e.sun_rise, e.sun_set, e.moon_rise, e.moon_set):
                if t is not None:
                    self.assertEqual(t.utcoffset(), datetime.timedelta(0))
                    self.assertEqual(t.astimezone(wit).date(), d)          # waktu jatuh pada tanggal WIT baris
        jan15 = rows[datetime.date(2026, 1, 15)]
        rise = jan15.sun_rise.astimezone(wit)
        self.assertEqual((rise.hour, rise.minute // 10), (5, 3))            # ±05:3x WIT
        self.assertIn("Purnama", fase_bulan(rows[datetime.date(2026, 1, 3)].moon_phase))
        self.assertIn("Bulan Baru", fase_bulan(rows[datetime.date(2026, 1, 19)].moon_phase))
        self.assertIn("Kuartal Ketiga", fase_bulan(rows[datetime.date(2026, 1, 11)].moon_phase))
