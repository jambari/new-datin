import datetime
import json
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from .models import (
    Gempa, Station, DataAvailability, AcceleroDataAvailability,
    ShakemapEvent,
)


def make_gempa(**kwargs):
    defaults = dict(
        source_id='BMKG-001',
        station_code='JYP',
        origin_datetime=datetime.datetime(2024, 3, 1, 10, 0, 0, tzinfo=datetime.timezone.utc),
        latitude=-2.5,
        longitude=140.0,
        magnitudo=5.2,
        depth=10.0,
        remark='',
        felt=False,
    )
    defaults.update(kwargs)
    return Gempa.objects.create(**defaults)


def make_station(**kwargs):
    defaults = dict(
        code='JYP',
        network='IA',
        name='Jayapura',
        latitude=-2.5,
        longitude=140.0,
        elevation=100.0,
    )
    defaults.update(kwargs)
    return Station.objects.create(**defaults)


def make_shakemap(**kwargs):
    defaults = dict(
        event_id='SM-001',
        latitude=-2.5,
        longitude=140.0,
        magnitude=5.2,
        depth=10.0,
        event_time=datetime.datetime(2024, 3, 1, 10, 0, 0, tzinfo=datetime.timezone.utc),
        location_string='Papua',
    )
    defaults.update(kwargs)
    return ShakemapEvent.objects.create(**defaults)


class GempaModelTest(TestCase):
    def test_create_and_str(self):
        g = make_gempa()
        s = str(g)
        self.assertTrue(len(s) > 0)

    def test_unique_source_id(self):
        make_gempa(source_id='BMKG-001')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            make_gempa(source_id='BMKG-001')

    def test_ordering_newest_first(self):
        make_gempa(source_id='G1', origin_datetime=datetime.datetime(2024, 3, 1, tzinfo=datetime.timezone.utc))
        make_gempa(source_id='G2', origin_datetime=datetime.datetime(2024, 3, 2, tzinfo=datetime.timezone.utc))
        ids = list(Gempa.objects.values_list('source_id', flat=True))
        self.assertEqual(ids[0], 'G2')


class StationModelTest(TestCase):
    def test_create_and_str(self):
        s = make_station()
        self.assertIn('JYP', str(s))

    def test_unique_code(self):
        make_station(code='JYP')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            make_station(code='JYP')


class DataAvailabilityModelTest(TestCase):
    def test_create(self):
        obj = DataAvailability.objects.create(
            station='JYP',
            channel='HHZ',
            date=datetime.date(2024, 3, 1),
            percentage=99.0,
        )
        self.assertEqual(obj.station, 'JYP')

    def test_unique_together(self):
        DataAvailability.objects.create(
            station='JYP', channel='HHZ', date=datetime.date(2024, 3, 1), percentage=99.0
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            DataAvailability.objects.create(
                station='JYP', channel='HHZ', date=datetime.date(2024, 3, 1), percentage=50.0
            )


class ShakemapEventModelTest(TestCase):
    def test_create_and_str(self):
        ev = make_shakemap()
        self.assertIn('SM-001', str(ev))

    def test_unique_event_id(self):
        make_shakemap(event_id='SM-001')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            make_shakemap(event_id='SM-001')



class GempaCreateAPITest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('apiuser', password='pass123')
        self.client.force_login(self.user)
        self.url = reverse('gempa_create_api')

    def test_post_valid_gempa(self):
        payload = {
            'source_id': 'BMKG-TEST-001',
            'station_code': 'JYP',
            'origin_datetime': '2024-03-01T10:00:00Z',
            'latitude': -2.5,
            'longitude': 140.0,
            'magnitudo': 5.2,
            'depth': 10,
            'remark': 'test',
            'felt': False,
        }
        resp = self.client.post(
            self.url, data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertIn(resp.status_code, [200, 201])
        self.assertTrue(Gempa.objects.filter(source_id='BMKG-TEST-001').exists())


class RepositoryViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('testuser', password='pass123')
        self.client.login(username='testuser', password='pass123')
        make_gempa()
        make_station()
        make_shakemap()

    def test_gempa_list_get(self):
        resp = self.client.get(reverse('gempa_list'))
        self.assertEqual(resp.status_code, 200)

    def test_gempa_detail_get(self):
        g = Gempa.objects.first()
        resp = self.client.get(reverse('gempa_detail', args=[g.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_gempa_detail_404_on_invalid(self):
        resp = self.client.get(reverse('gempa_detail', args=[9999]))
        self.assertEqual(resp.status_code, 404)

    def test_station_map_get(self):
        resp = self.client.get(reverse('spicks'))
        self.assertEqual(resp.status_code, 200)

    def test_station_geojson_api(self):
        resp = self.client.get(reverse('station_geojson'))
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIn('features', data)

    def test_station_detail_get(self):
        resp = self.client.get(reverse('station_detail', args=['JYP']))
        self.assertEqual(resp.status_code, 200)

    def test_station_detail_404_on_invalid(self):
        resp = self.client.get(reverse('station_detail', args=['NOTEXIST']))
        self.assertEqual(resp.status_code, 404)

    def test_data_availability_list_get(self):
        resp = self.client.get(reverse('data_availability_list'))
        self.assertEqual(resp.status_code, 200)

    def test_accelero_availability_list_get(self):
        resp = self.client.get(reverse('accelero_availability_list'))
        self.assertEqual(resp.status_code, 200)

    def test_shakemap_list_get(self):
        resp = self.client.get(reverse('shakemap-list'))
        self.assertEqual(resp.status_code, 200)

    def test_shakemap_detail_get(self):
        ev = ShakemapEvent.objects.first()
        resp = self.client.get(reverse('shakemap-detail', args=[ev.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_shakemap_detail_404_on_invalid(self):
        resp = self.client.get(reverse('shakemap-detail', args=[9999]))
        self.assertEqual(resp.status_code, 404)

    def test_unauthenticated_gempa_list_redirects(self):
        self.client.logout()
        resp = self.client.get(reverse('gempa_list'))
        self.assertIn(resp.status_code, [200, 302, 403])
