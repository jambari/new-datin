import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User, Group
from .models import Logbook


def make_user(username='officer', password='pass123'):
    return User.objects.create_user(username, password=password)


def make_logbook(user, **kwargs):
    defaults = dict(
        petugas=user,
        tanggal=datetime.date(2024, 3, 1),
        shift='Pagi',
        status_absen='Masuk',
        seiscomp_seismik='ON',
        seiscomp_accelero='ON',
        esdx='ON',
        petir='OFF',
        lemi='ON',
        proton='OFF',
    )
    defaults.update(kwargs)
    return Logbook.objects.create(**defaults)


class LogbookModelTest(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_create_and_str(self):
        log = make_logbook(self.user)
        self.assertIn('2024-03-01', str(log))
        self.assertIn('Pagi', str(log))

    def test_default_status_values(self):
        log = make_logbook(self.user)
        self.assertEqual(log.seiscomp_seismik, 'ON')
        self.assertEqual(log.proton, 'OFF')

    def test_ordering_newest_first(self):
        make_logbook(self.user, tanggal=datetime.date(2024, 3, 1))
        make_logbook(self.user, tanggal=datetime.date(2024, 3, 2))
        logs = Logbook.objects.all()
        self.assertEqual(logs[0].tanggal, datetime.date(2024, 3, 2))

    def test_m2m_previous_officers(self):
        log = make_logbook(self.user)
        other = make_user('other')
        log.petugas_sebelum.add(other)
        self.assertIn(other, log.petugas_sebelum.all())

    def test_m2m_next_officers(self):
        log = make_logbook(self.user)
        other = make_user('other')
        log.petugas_selanjutnya.add(other)
        self.assertIn(other, log.petugas_selanjutnya.all())


class LogbookViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user()
        self.log = make_logbook(self.user)

    def test_index_from_allowed_ip_returns_200(self):
        resp = self.client.get(
            reverse('logbook:logbook_list'),
            REMOTE_ADDR='127.0.0.1',
        )
        self.assertEqual(resp.status_code, 200)

    def test_index_from_unauthorized_ip_returns_200_with_error(self):
        resp = self.client.get(
            reverse('logbook:logbook_list'),
            REMOTE_ADDR='1.2.3.4',
        )
        self.assertEqual(resp.status_code, 200)

    def test_print_log_detail_get(self):
        resp = self.client.get(
            reverse('logbook:print_log_detail', args=[self.log.id]),
            REMOTE_ADDR='127.0.0.1',
        )
        self.assertEqual(resp.status_code, 200)

    def test_print_log_detail_404_on_invalid(self):
        resp = self.client.get(
            reverse('logbook:print_log_detail', args=[9999]),
            REMOTE_ADDR='127.0.0.1',
        )
        self.assertEqual(resp.status_code, 404)

    def test_edit_log_get_from_allowed_ip(self):
        resp = self.client.get(
            reverse('logbook:edit_log', args=[self.log.id]),
            REMOTE_ADDR='127.0.0.1',
        )
        self.assertIn(resp.status_code, [200, 302, 403])

    def test_edit_log_404_on_invalid(self):
        resp = self.client.get(
            reverse('logbook:edit_log', args=[9999]),
            REMOTE_ADDR='127.0.0.1',
        )
        self.assertEqual(resp.status_code, 404)


class LogbookShakemapReminderTest(TestCase):
    """Modal pengingat shakemap di halaman logbook."""

    URL = '/logbook/'

    def test_modal_markup_present_for_allowed_ip(self):
        resp = self.client.get(self.URL, REMOTE_ADDR='127.0.0.1')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="shakemap-reminder"')
        self.assertContains(resp, 'id="shakemap-reminder-close"')
        self.assertContains(resp, 'Ops sayang, tolong generate tiap gempa')

    def test_modal_message_mentions_threshold(self):
        resp = self.client.get(self.URL, REMOTE_ADDR='127.0.0.1')
        # Pesan harus menyebut ambang magnitudo 3.6 dengan '>' ter-escape.
        self.assertContains(resp, 'M&gt;=3.6')

    def test_modal_absent_for_unauthorized_ip(self):
        resp = self.client.get(self.URL, REMOTE_ADDR='1.2.3.4')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Akses Ditolak')
        self.assertNotContains(resp, 'id="shakemap-reminder"')
        self.assertNotContains(resp, 'Ops sayang')

    def test_modal_triggers_on_window_load(self):
        """Popup dipicu oleh window 'load' (halaman 100% termuat), bukan DOMContentLoaded."""
        resp = self.client.get(self.URL, REMOTE_ADDR='127.0.0.1')
        self.assertContains(resp, "window.addEventListener('load'")

    def test_print_view_has_no_modal(self):
        user = make_user('printer')
        log = make_logbook(user)
        resp = self.client.get(
            reverse('logbook:print_log_detail', args=[log.id]),
            REMOTE_ADDR='127.0.0.1',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'shakemap-reminder')


class LogbookSirineGateTest(TestCase):
    """Submit logbook ditahan sampai tombol Cek Sirene (ping) diklik."""

    URL = '/logbook/'

    def test_gate_present_for_allowed_ip(self):
        resp = self.client.get(self.URL, REMOTE_ADDR='127.0.0.1')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Oops, belum cek sirine')
        self.assertContains(resp, 'sireneChecked')

    def test_gate_absent_for_unauthorized_ip(self):
        resp = self.client.get(self.URL, REMOTE_ADDR='1.2.3.4')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Akses Ditolak')
        self.assertNotContains(resp, 'id="btn-cek-sirine"')


# ── Cek sirene (ping) ────────────────────────────────────────────────────────
from unittest import mock

from django.core.cache import cache
from django.test import override_settings

from .sirine import (ALLOWED_ACTION, SirineAuthError, SirineCheckError,
                     SirineClient, SirineSafetyError, build_action_url,
                     parse_ping_message)

BASE = 'https://sirine.id:8088'
DEVICE = '876d4fcf47'


class _FakeResponse:
    def __init__(self, status_code=200, text='', payload=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError('no json')
        return self._payload


class _FakeSession:
    """Session palsu: mencatat setiap URL yang dipanggil (untuk audit keamanan)."""

    def __init__(self, responses):
        self.headers = {}
        self._responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method.upper(), url))
        if not self._responses:
            raise AssertionError(f'request tak terduga: {method} {url}')
        return self._responses.pop(0)


class SirineSafetyTest(TestCase):
    """Sirene tsunami: pastikan tidak ada jalan memanggil aksi membunyikan."""

    def test_build_action_url_only_allows_ping(self):
        self.assertTrue(
            build_action_url(BASE, DEVICE).endswith(f'/activate/{DEVICE}/ping'))

    def test_build_action_url_refuses_real(self):
        with self.assertRaises(SirineSafetyError):
            build_action_url(BASE, DEVICE, 'real')

    def test_build_action_url_refuses_test(self):
        with self.assertRaises(SirineSafetyError):
            build_action_url(BASE, DEVICE, 'test')

    def test_build_action_url_refuses_unknown_action(self):
        for action in ['', 'play', 'start', 'stop', 'trigger', 'bunyi',
                       'alarm', 'activate', 'REAL', 'Ping2']:
            with self.subTest(action=action):
                with self.assertRaises(SirineSafetyError):
                    build_action_url(BASE, DEVICE, action)

    def test_guard_blocks_the_real_and_test_endpoints(self):
        client = SirineClient(BASE, 'u', 'p', DEVICE, session=_FakeSession([]))
        for path in [f'/activate/{DEVICE}/real', f'/activate/{DEVICE}/test',
                     f'/activate/{DEVICE}/play', f'/activate/{DEVICE}/stop']:
            with self.subTest(path=path):
                with self.assertRaises(SirineSafetyError):
                    client._guard('GET', BASE + path)

    def test_guard_blocks_get_to_activate_without_ping(self):
        client = SirineClient(BASE, 'u', 'p', DEVICE, session=_FakeSession([]))
        with self.assertRaises(SirineSafetyError):
            client._guard('GET', f'{BASE}/activate/{DEVICE}/')

    def test_guard_blocks_post_anywhere_but_login(self):
        client = SirineClient(BASE, 'u', 'p', DEVICE, session=_FakeSession([]))
        with self.assertRaises(SirineSafetyError):
            client._guard('POST', f'{BASE}/activate/{DEVICE}/ping')

    def test_ping_flow_never_touches_a_forbidden_url(self):
        """Audit: sepanjang alur ping, tidak ada satu pun URL terlarang."""
        session = _FakeSession([
            _FakeResponse(200, text='<input name="csrfmiddlewaretoken" value="tok">'),
            _FakeResponse(302),
            _FakeResponse(200, payload={'data': {'message': '4 packets transmitted, 4 received, 0% packet loss, time 3001ms'}}),
        ])
        client = SirineClient(BASE, 'u', 'p', DEVICE, session=session)
        result = client.ping()

        self.assertEqual(result.status, 'ON')
        for method, url in session.calls:
            with self.subTest(url=url):
                self.assertNotIn('/real', url)
                self.assertNotIn('/test', url)
                for bad in ['play', 'trigger', 'bunyi', 'alarm', 'stop']:
                    self.assertNotIn(bad, url)
        # hanya satu POST, yaitu login
        self.assertEqual([m for m, _ in session.calls].count('POST'), 1)
        self.assertEqual(session.calls[1][1], f'{BASE}/login/')


class SirineParseTest(TestCase):
    def test_four_of_four_zero_loss_is_on(self):
        r = parse_ping_message('\n4 packets transmitted, 4 received, 0% packet loss, time 3006ms')
        self.assertEqual((r.transmitted, r.received, r.loss_percent), (4, 4, 0))
        self.assertEqual(r.status, 'ON')
        self.assertTrue(r.is_on)

    def test_total_loss_is_off(self):
        r = parse_ping_message('4 packets transmitted, 0 received, 100% packet loss, time 3005ms')
        self.assertEqual(r.status, 'OFF')

    def test_partial_loss_is_off(self):
        r = parse_ping_message('4 packets transmitted, 3 received, 25% packet loss, time 3004ms')
        self.assertEqual(r.status, 'OFF')

    def test_unparseable_message_raises(self):
        for bad in ['', 'ping timeout', 'Destination Host Unreachable']:
            with self.subTest(message=bad):
                with self.assertRaises(SirineCheckError):
                    parse_ping_message(bad)


class SirineClientFlowTest(TestCase):
    def _client(self, responses):
        return SirineClient(BASE, 'u', 'p', DEVICE, session=_FakeSession(responses))

    def test_login_failure_raises_auth_error(self):
        client = self._client([
            _FakeResponse(200, text='<input name="csrfmiddlewaretoken" value="tok">'),
            _FakeResponse(200),          # form diulang = ditolak
        ])
        with self.assertRaises(SirineAuthError):
            client.ping()

    def test_missing_csrf_raises_auth_error(self):
        client = self._client([_FakeResponse(200, text='<html>tanpa token</html>')])
        with self.assertRaises(SirineAuthError):
            client.ping()

    def test_non_json_reply_raises_check_error(self):
        client = self._client([
            _FakeResponse(200, text='<input name="csrfmiddlewaretoken" value="tok">'),
            _FakeResponse(302),
            _FakeResponse(200, text='<html>login</html>'),   # bukan JSON
        ])
        with self.assertRaises(SirineCheckError):
            client.ping()

    def test_missing_device_id_raises_sirine_error(self):
        with self.assertRaises(Exception):
            SirineClient(BASE, 'u', 'p', '')


@override_settings(SIRINE_BASE_URL=BASE, SIRINE_USER='u', SIRINE_PASS='p',
                   SIRINE_DEVICE_ID=DEVICE, SIRINE_COOLDOWN_SECONDS=15)
class SirineCheckViewTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.url = reverse('logbook:sirine_check')

    def tearDown(self):
        cache.clear()

    def _ping_result(self, status='ON'):
        from .sirine import PingResult
        return PingResult(transmitted=4, received=4 if status == 'ON' else 0,
                          loss_percent=0 if status == 'ON' else 100,
                          status=status, message='4 packets transmitted, '
                          f'{4 if status == "ON" else 0} received')

    def test_ping_returns_status_as_json(self):
        with mock.patch('logbook.views.SirineClient') as client_cls:
            client_cls.return_value.ping.return_value = self._ping_result('ON')
            resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['status'], 'ON')
        self.assertEqual(data['received'], 4)
        self.assertEqual(data['loss_percent'], 0)

    def test_off_result_is_returned(self):
        with mock.patch('logbook.views.SirineClient') as client_cls:
            client_cls.return_value.ping.return_value = self._ping_result('OFF')
            resp = self.client.post(self.url)
        self.assertEqual(resp.json()['status'], 'OFF')

    def test_failure_returns_error_and_does_not_claim_a_status(self):
        with mock.patch('logbook.views.SirineClient') as client_cls:
            client_cls.return_value.ping.side_effect = SirineAuthError('login ditolak')
            resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 502)
        data = resp.json()
        self.assertFalse(data['ok'])
        self.assertIn('login ditolak', data['error'])
        self.assertNotIn('status', data)       # jangan menulis status palsu

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_ip_outside_office_is_refused(self):
        with mock.patch('logbook.views.get_client_ip', return_value='8.8.8.8'):
            resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 403)

    def test_double_click_is_rate_limited(self):
        with mock.patch('logbook.views.SirineClient') as client_cls:
            client_cls.return_value.ping.return_value = self._ping_result('ON')
            first = self.client.post(self.url)
            second = self.client.post(self.url)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)

    def test_cooldown_released_after_a_failure_so_retry_is_possible(self):
        with mock.patch('logbook.views.SirineClient') as client_cls:
            client_cls.return_value.ping.side_effect = SirineCheckError('gagal')
            self.assertEqual(self.client.post(self.url).status_code, 502)
            client_cls.return_value.ping.side_effect = None
            client_cls.return_value.ping.return_value = self._ping_result('ON')
            self.assertEqual(self.client.post(self.url).status_code, 200)


class SireneOffModalTest(TestCase):
    """Kalau hasil ping = OFF, muncul modal "kontak rekanan"."""

    URL = '/logbook/'

    def test_modal_markup_present_for_allowed_ip(self):
        resp = self.client.get(self.URL, REMOTE_ADDR='127.0.0.1')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="sirene-off-modal"')
        self.assertContains(resp, 'id="sirene-off-close"')
        self.assertContains(resp, 'Sirene OFF')

    def test_modal_shows_the_vendor_contact(self):
        resp = self.client.get(self.URL, REMOTE_ADDR='127.0.0.1')
        self.assertContains(resp, 'kontak rekanan')
        self.assertContains(resp, '0812 8773 8748')
        # nomor bisa langsung ditelepon dari ponsel
        self.assertContains(resp, 'tel:+6281287738748')

    def test_modal_absent_for_unauthorized_ip(self):
        resp = self.client.get(self.URL, REMOTE_ADDR='1.2.3.4')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Akses Ditolak')
        self.assertNotContains(resp, 'id="sirene-off-modal"')
        self.assertNotContains(resp, 'tel:+6281287738748')   # hanya ada di markup modal

    def test_modal_opens_only_when_result_is_off(self):
        resp = self.client.get(self.URL, REMOTE_ADDR='127.0.0.1')
        html = resp.content.decode()
        self.assertIn("if (d.status === 'OFF')", html)
        self.assertIn('openOffModal(d.message)', html)

    def test_modal_not_shown_when_the_check_fails(self):
        """Gagal cek bukan berarti OFF — jangan menyuruh kontak rekanan."""
        resp = self.client.get(self.URL, REMOTE_ADDR='127.0.0.1')
        html = resp.content.decode()
        # cabang gagal keluar lebih dulu dan tidak memanggil openOffModal
        fail_branch = html[html.index("if (!d.ok) {"):html.index("if (select) select.value")]
        self.assertNotIn('openOffModal', fail_branch)

    def test_modal_hidden_when_printing(self):
        """Aturan cetak menyembunyikan semua .reminder-overlay."""
        resp = self.client.get(self.URL, REMOTE_ADDR='127.0.0.1')
        self.assertContains(resp, '.reminder-overlay { display: none !important; }')
