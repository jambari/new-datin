import datetime
import json
from django.test import TestCase, Client, override_settings
from django.test import RequestFactory
from django.middleware.security import SecurityMiddleware
from django.urls import reverse
from django.contrib.auth.models import User
from .models import WRSNGStatus, WRSNGDataAvailability


def make_status(**kwargs):
    defaults = dict(
        status_datetime=datetime.datetime(2024, 3, 1, 10, 0, 0, tzinfo=datetime.timezone.utc),
        wrs_code='WRS-01',
        latitude=-2.5,
        longitude=140.0,
        display_status=1,
        chrome_status=1,
    )
    defaults.update(kwargs)
    return WRSNGStatus.objects.create(**defaults)


class WRSNGStatusModelTest(TestCase):
    def test_create_and_str(self):
        s = make_status()
        self.assertIn('WRS-01', str(s))

    def test_ordering_newest_first(self):
        make_status(
            wrs_code='WRS-01',
            status_datetime=datetime.datetime(2024, 3, 1, tzinfo=datetime.timezone.utc),
        )
        make_status(
            wrs_code='WRS-02',
            status_datetime=datetime.datetime(2024, 3, 2, tzinfo=datetime.timezone.utc),
        )
        first = WRSNGStatus.objects.first()
        self.assertEqual(first.wrs_code, 'WRS-02')


class WRSNGDataAvailabilityModelTest(TestCase):
    def test_create(self):
        obj = WRSNGDataAvailability.objects.create(
            station='WRS-01',
            date=datetime.date(2024, 3, 1),
            percentage=100.0,
        )
        self.assertIn('WRS-01', str(obj))

    def test_unique_together(self):
        WRSNGDataAvailability.objects.create(
            station='WRS-01', date=datetime.date(2024, 3, 1), percentage=100.0
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            WRSNGDataAvailability.objects.create(
                station='WRS-01', date=datetime.date(2024, 3, 1), percentage=50.0
            )


class WRSNGStatusUpdateAPITest(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse('wrsng:status_update_api')

    def test_post_valid_status(self):
        payload = {
            'status_datetime': '2024-03-01T10:00:00Z',
            'wrs_code': 'WRS-01',
            'latitude': -2.5,
            'longitude': 140.0,
            'display_status': 1,
            'chrome_status': 1,
        }
        resp = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertIn(resp.status_code, [200, 201])

    def test_get_not_allowed(self):
        resp = self.client.get(self.url)
        self.assertIn(resp.status_code, [400, 405])


class WRSNGViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('testuser', password='pass123')
        self.client.login(username='testuser', password='pass123')
        make_status()

    def test_status_list_get(self):
        resp = self.client.get(reverse('wrsng:status_list'))
        self.assertEqual(resp.status_code, 200)

    def test_status_list_filter_by_code(self):
        resp = self.client.get(reverse('wrsng:status_list'), {'wrs_code': 'WRS-01'})
        self.assertEqual(resp.status_code, 200)

    def test_status_list_filter_by_date(self):
        resp = self.client.get(reverse('wrsng:status_list'), {
            'start_date': '2024-01-01',
            'end_date': '2024-12-31',
        })
        self.assertEqual(resp.status_code, 200)

    def test_wrsng_availability_query_get(self):
        resp = self.client.get(reverse('wrsng:wrsng_availability_query'))
        self.assertEqual(resp.status_code, 200)

    def test_update_availability_post(self):
        payload = {'station': 'WRS-01', 'date': '2024-03-01', 'value': 98.0}
        resp = self.client.post(
            reverse('wrsng:update_wrsng_availability'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertIn(resp.status_code, [200, 201])

    def test_unauthenticated_status_list_redirects(self):
        self.client.logout()
        resp = self.client.get(reverse('wrsng:status_list'))
        self.assertIn(resp.status_code, [200, 302, 403])


class SecureRedirectExemptTest(TestCase):
    """Ingest API harus tetap bisa di-POST lewat plain HTTP.

    Perangkat WRSNG (dan monitor instrumen) tidak mengikuti redirect 301,
    sehingga begitu SECURE_SSL_REDIRECT diaktifkan datanya hilang kecuali
    path-nya dikecualikan di SECURE_REDIRECT_EXEMPT (dan di-proxy nginx port 80).
    """

    EXEMPT_PATHS = [
        '/api/wrsng/status/update/',
        '/api/yolo/state/',
        '/api/yolo/snapshot/',
        '/magnet/api/instrument/status/',
    ]

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_ingest_paths_are_not_redirected_over_http(self):
        middleware = SecurityMiddleware(lambda request: None)
        for path in self.EXEMPT_PATHS:
            with self.subTest(path=path):
                request = RequestFactory().post(path, secure=False)
                self.assertIsNone(
                    middleware.process_request(request),
                    f'{path} tidak boleh di-redirect ke HTTPS',
                )

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_other_paths_still_redirect_to_https(self):
        middleware = SecurityMiddleware(lambda request: None)
        request = RequestFactory().get('/wrsng/status/list/', secure=False)
        response = middleware.process_request(request)
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 301)

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_exempt_paths_are_reachable_over_https_too(self):
        """HTTPS tidak boleh terpengaruh oleh pengecualian ini."""
        middleware = SecurityMiddleware(lambda request: None)
        request = RequestFactory().post('/api/wrsng/status/update/', secure=True)
        self.assertIsNone(middleware.process_request(request))

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_ingest_post_survives_the_redirect_middleware(self):
        """End-to-end lewat middleware: POST HTTP harus sampai ke view (bukan 301).

        Perangkat WRSNG memakai path /api/wrsng/status/update/ (lihat README dan
        nginx access log), bukan /wrsng/status/update/ dari namespace app.
        """
        payload = {
            'status_datetime': '2024-03-01T10:00:00Z',
            'wrs_code': 'WRS-01',
            'display_status': 1,
            'chrome_status': 1,
        }
        resp = self.client.post(
            '/api/wrsng/status/update/',
            data=json.dumps(payload),
            content_type='application/json',
            secure=False,
        )
        self.assertIn(resp.status_code, [200, 201], f'dapat {resp.status_code}, bukan 301')
        self.assertTrue(WRSNGStatus.objects.filter(wrs_code='WRS-01').exists())

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_app_namespaced_route_still_redirects(self):
        """Route duplikat /wrsng/status/update/ tidak dikecualikan (bukan jalur device)."""
        resp = self.client.post(
            reverse('wrsng:status_update_api'),
            data='{}',
            content_type='application/json',
            secure=False,
        )
        self.assertEqual(resp.status_code, 301)
