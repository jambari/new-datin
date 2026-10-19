import datetime
import json
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from .models import Strike, DailyStrikeSummary, LightningDataAvailability


def make_strike(**kwargs):
    defaults = dict(
        epoch_ms=1700000000000,
        timestamp=datetime.datetime(2024, 3, 1, 10, 0, 0, tzinfo=datetime.timezone.utc),
        latitude=-2.5,
        longitude=140.0,
        strike_type=0,
    )
    defaults.update(kwargs)
    return Strike.objects.create(**defaults)


def make_summary(**kwargs):
    defaults = dict(
        summary_date=datetime.date(2024, 3, 1),
        cg_plus_count=10,
        cg_minus_count=20,
        ic_count=5,
        other_count=1,
        total_count=36,
    )
    defaults.update(kwargs)
    return DailyStrikeSummary.objects.create(**defaults)


class StrikeModelTest(TestCase):
    def test_create(self):
        s = make_strike()
        self.assertEqual(s.latitude, -2.5)
        self.assertEqual(s.strike_type, 0)

    def test_bulk_create(self):
        strikes = [
            Strike(
                epoch_ms=1700000000000 + i,
                timestamp=datetime.datetime(2024, 3, 1, 10, i, 0, tzinfo=datetime.timezone.utc),
                latitude=-2.5,
                longitude=140.0,
                strike_type=0,
            )
            for i in range(5)
        ]
        Strike.objects.bulk_create(strikes)
        self.assertEqual(Strike.objects.count(), 5)


class DailyStrikeSummaryModelTest(TestCase):
    def test_create_and_str(self):
        s = make_summary()
        self.assertIn('2024-03-01', str(s))

    def test_unique_summary_date(self):
        make_summary(summary_date=datetime.date(2024, 3, 1))
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            make_summary(summary_date=datetime.date(2024, 3, 1))

    def test_ordering_newest_first(self):
        make_summary(summary_date=datetime.date(2024, 3, 1))
        make_summary(summary_date=datetime.date(2024, 3, 2))
        dates = list(DailyStrikeSummary.objects.values_list('summary_date', flat=True))
        self.assertEqual(dates[0], datetime.date(2024, 3, 2))


class LightningDataAvailabilityModelTest(TestCase):
    def test_create(self):
        obj = LightningDataAvailability.objects.create(
            station='JAYAPURA',
            date=datetime.date(2024, 3, 1),
            percentage=100.0,
        )
        self.assertIn('JAYAPURA', str(obj))

    def test_unique_together(self):
        LightningDataAvailability.objects.create(
            station='JAYAPURA', date=datetime.date(2024, 3, 1), percentage=100.0
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            LightningDataAvailability.objects.create(
                station='JAYAPURA', date=datetime.date(2024, 3, 1), percentage=50.0
            )


class LightningViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('testuser', password='pass123')
        self.client.login(username='testuser', password='pass123')
        make_strike()
        make_summary()

    def test_nexstorm_query_page_get(self):
        resp = self.client.get(reverse('lightning:nexstorm_query_page'))
        self.assertEqual(resp.status_code, 200)

    def test_nexstorm_query_api_get(self):
        resp = self.client.get(reverse('lightning:nexstorm_query_api'))
        self.assertEqual(resp.status_code, 200)

    def test_lightning_availability_query_get(self):
        resp = self.client.get(reverse('lightning:lightning_availability_query'))
        self.assertEqual(resp.status_code, 200)

    def test_upload_nexstorm_get(self):
        resp = self.client.get(reverse('lightning:upload_nexstorm'))
        self.assertEqual(resp.status_code, 200)

    def test_update_availability_post(self):
        payload = {'station': 'JAYAPURA', 'date': '2024-03-01', 'percentage': 99.0}
        resp = self.client.post(
            reverse('lightning:update_lightning_availability'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertIn(resp.status_code, [200, 201])

    def test_delete_all_strikes_post(self):
        resp = self.client.post(reverse('lightning:strike_delete_all'))
        self.assertIn(resp.status_code, [200, 302])
        self.assertEqual(Strike.objects.count(), 0)

    def test_unauthenticated_redirects(self):
        self.client.logout()
        resp = self.client.get(reverse('lightning:nexstorm_query_page'))
        self.assertIn(resp.status_code, [200, 302, 403])


class LightningGridKotaJayapuraTest(TestCase):
    def setUp(self):
        from .models import LightningMonthlyGrid
        self.client.force_login(User.objects.create_user('petir', password='x'))
        cells = [(-2.53, 140.71, 3, 4),     # Jayapura Utara
                 (-2.60, 140.65, 1, 1),     # Heram / Abepura
                 (-2.60, 140.34, 7, 6),     # Sentani (di luar Kota Jayapura)
                 (-2.20, 140.90, 2, 0)]     # laut
        for lat, lon, plus, minus in cells:
            LightningMonthlyGrid.objects.create(year=2026, month=6, latitude=lat, longitude=lon, cg_plus=plus,
                                                cg_minus=minus, total=plus + minus, idw_smooth=plus + minus)

    def test_summary_counts_only_cells_inside_city(self):
        r = self.client.get('/lightning/grid/', {'year': 2026, 'month': 6})
        self.assertEqual(r.status_code, 200)
        kj = r.context['kota_jayapura']
        self.assertEqual(kj['total'], {'cells': 2, 'cg_plus': 4, 'cg_minus': 5, 'total': 9})
        self.assertEqual(kj['rows'][0], {'name': 'Jayapura Utara', 'cells': 1, 'cg_plus': 3, 'cg_minus': 4, 'total': 7})
        self.assertEqual(len(kj['rows']), 5)
        self.assertContains(r, 'Potong ke batas Kota Jayapura')
        self.assertContains(r, 'kota_jayapura.geojson')

    def test_layout_png(self):
        from unittest import mock
        from PIL import Image
        tile = lambda z, x, y: Image.new("RGB", (256, 256), (200, 220, 240))
        with mock.patch("reporting.osm._tile", side_effect=tile):
            r = self.client.get('/lightning/grid/layout/', {'year': 2026, 'month': 6})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'image/png')
        self.assertTrue(r['Content-Disposition'].startswith('inline;'))
        self.assertIn('peta_kerapatan_petir_kota_jayapura_2026_06.png', r['Content-Disposition'])
        with mock.patch("reporting.osm._tile", side_effect=tile):
            d = self.client.get('/lightning/grid/layout/', {'year': 2026, 'month': 6, 'download': 1})
        self.assertTrue(d['Content-Disposition'].startswith('attachment;'))
        self.assertEqual(Image.open(__import__('io').BytesIO(r.content)).size, (1800, 1245))
        self.assertEqual(self.client.get('/lightning/grid/layout/').status_code, 400)
        page = self.client.get('/lightning/grid/', {'year': 2026, 'month': 6})
        self.assertContains(page, 'Layout Peta Kota Jayapura')
        self.assertContains(page, 'data-src="/lightning/grid/layout/?year=2026&month=6"')
        self.assertContains(page, '/lightning/grid/layout/?year=2026&month=6&download=1')
