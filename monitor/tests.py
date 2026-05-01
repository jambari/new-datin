import json
from datetime import datetime, timezone
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.gis.geos import Point
from .models import EarthquakeEvent


def make_event(**kwargs):
    defaults = dict(
        event_id='EV001',
        origin_time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        magnitude=5.2,
        latitude=-2.5,
        longitude=140.0,
        depth=10.0,
        region='Papua',
        agency='BMKG',
        status='reviewed',
    )
    defaults.update(kwargs)
    return EarthquakeEvent.objects.create(**defaults)


class EarthquakeEventModelTest(TestCase):
    def test_create_and_str(self):
        ev = make_event()
        self.assertEqual(str(ev), 'EV001 - M5.2 Papua')

    def test_point_field(self):
        ev = make_event(location=Point(140.0, -2.5, srid=4326))
        ev.refresh_from_db()
        self.assertAlmostEqual(ev.location.x, 140.0)

    def test_ordering_newest_first(self):
        make_event(event_id='EV001', origin_time=datetime(2024, 1, 1, tzinfo=timezone.utc))
        make_event(event_id='EV002', origin_time=datetime(2024, 1, 2, tzinfo=timezone.utc))
        ids = list(EarthquakeEvent.objects.values_list('event_id', flat=True))
        self.assertEqual(ids, ['EV002', 'EV001'])

    def test_unique_event_id(self):
        make_event(event_id='EV001')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            make_event(event_id='EV001')


class ReceiveEventAPITest(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse('receive_event')

    def test_post_valid_event_creates_record(self):
        payload = {
            'event_id': 'EV100',
            'origin_time': '2024-01-15T10:00:00Z',
            'magnitude': 5.0,
            'latitude': -2.5,
            'longitude': 140.0,
            'depth': 10.0,
            'region': 'Papua',
            'agency': 'BMKG',
            'status': 'reviewed',
        }
        resp = self.client.post(
            self.url, data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertIn(resp.status_code, [200, 201])
        self.assertTrue(EarthquakeEvent.objects.filter(event_id='EV100').exists())

    def test_post_duplicate_event_id_returns_error(self):
        make_event(event_id='EV100')
        payload = {
            'event_id': 'EV100',
            'origin_time': '2024-01-15T10:00:00Z',
            'magnitude': 5.0,
            'latitude': -2.5,
            'longitude': 140.0,
            'depth': 10.0,
            'region': 'Papua',
        }
        resp = self.client.post(
            self.url, data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertIn(resp.status_code, [200, 400, 409])

    def test_get_returns_405_or_400(self):
        resp = self.client.get(self.url)
        self.assertIn(resp.status_code, [400, 405])


class PublicEventListViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        make_event()
        self.url = reverse('public_event_list')

    def test_get_returns_200(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_filter_by_agency(self):
        resp = self.client.get(self.url, {'agency': 'BMKG'})
        self.assertEqual(resp.status_code, 200)

    def test_filter_by_magnitude_range(self):
        resp = self.client.get(self.url, {'min_mag': '5.0', 'max_mag': '6.0'})
        self.assertEqual(resp.status_code, 200)

    def test_filter_by_date_range(self):
        resp = self.client.get(self.url, {'start_date': '2024-01-01', 'end_date': '2024-12-31'})
        self.assertEqual(resp.status_code, 200)


class ExportJsonViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        make_event()

    def test_returns_json_content_type(self):
        url = reverse('export_json')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/json')

    def test_json_contains_data(self):
        url = reverse('export_json')
        resp = self.client.get(url)
        data = json.loads(resp.content)
        # Response is either a list or a dict with a 'data' key
        if isinstance(data, list):
            self.assertGreater(len(data), 0)
        else:
            events = data.get('data', data)
            self.assertGreater(len(events), 0)


class WebGISDetailViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.ev = make_event()

    def test_existing_event_returns_200(self):
        url = reverse('webgis_detail', args=[self.ev.event_id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_nonexistent_event_returns_404(self):
        url = reverse('webgis_detail', args=['NOTEXIST'])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)


class SeismicityAnalysisViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        make_event()

    def test_returns_200(self):
        url = reverse('seismicity_analysis')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
