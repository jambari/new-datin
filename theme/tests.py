import datetime
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice

from theme.views import bartington_form_open


def _code(device):
    device.refresh_from_db()
    return format(totp(device.bin_key, device.step, device.t0,
                       device.digits, device.drift), '06d')


class LoginOTPTest(TestCase):
    """/accounts/login/: users with a confirmed OTP device must enter a code."""

    def setUp(self):
        self.user = User.objects.create_user('pegawai', password='rahasiaku123')

    def _login(self, **extra):
        return self.client.post('/accounts/login/' + extra.pop('qs', ''),
                                {'username': 'pegawai', 'password': 'rahasiaku123', **extra})

    def _is_logged_in(self):
        return '_auth_user_id' in self.client.session

    def test_user_without_otp_goes_straight_in(self):
        resp = self._login()
        self.assertEqual(resp['Location'], '/post-login/')
        self.assertTrue(self._is_logged_in())

    def test_unconfirmed_device_does_not_ask_for_otp(self):
        TOTPDevice.objects.create(user=self.user, name='default', confirmed=False)
        self.assertEqual(self._login()['Location'], '/post-login/')

    def test_user_with_otp_is_asked_for_a_code_and_not_logged_in_yet(self):
        TOTPDevice.objects.create(user=self.user, name='default', confirmed=True)
        resp = self._login()
        self.assertEqual(resp['Location'], '/accounts/otp-verify/')
        self.assertFalse(self._is_logged_in())
        # Skipping the OTP page must not give access
        resp = self.client.get('/dashboard/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp['Location'])
        page = self.client.get('/accounts/otp-verify/')
        self.assertContains(page, 'pegawai')

    def test_correct_code_logs_in_verified_and_keeps_next(self):
        device = TOTPDevice.objects.create(user=self.user, name='default', confirmed=True)
        self._login(qs='?next=/logbook/', next='/logbook/')
        resp = self.client.post('/accounts/otp-verify/', {'otp_token': _code(device)})
        self.assertEqual(resp['Location'], '/logbook/')
        self.assertTrue(self._is_logged_in())
        self.assertIn('otp_device_id', self.client.session)
        self.assertNotIn('pre_otp', self.client.session)

    def test_verified_session_opens_admin_without_second_otp(self):
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        device = TOTPDevice.objects.create(user=self.user, name='default', confirmed=True)
        self._login()
        self.client.post('/accounts/otp-verify/', {'otp_token': _code(device)})
        self.assertEqual(self.client.get('/admin/').status_code, 200)

    def test_wrong_code_is_rejected(self):
        TOTPDevice.objects.create(user=self.user, name='default', confirmed=True)
        self._login()
        resp = self.client.post('/accounts/otp-verify/', {'otp_token': '000000'})
        self.assertContains(resp, 'Kode OTP tidak valid')
        self.assertFalse(self._is_logged_in())

    def test_too_many_wrong_codes_restart_the_login(self):
        TOTPDevice.objects.create(user=self.user, name='default', confirmed=True)
        self._login()
        with mock.patch('theme.views.match_token', return_value=None):
            for _ in range(4):
                self.client.post('/accounts/otp-verify/', {'otp_token': '000000'})
            resp = self.client.post('/accounts/otp-verify/', {'otp_token': '000000'})
        self.assertEqual(resp['Location'], '/accounts/login/')
        self.assertNotIn('pre_otp', self.client.session)

    def test_otp_step_expires(self):
        TOTPDevice.objects.create(user=self.user, name='default', confirmed=True)
        with mock.patch('theme.views.time.time', return_value=1_000_000):
            self._login()
        with mock.patch('theme.views.time.time', return_value=1_000_000 + 301):
            resp = self.client.get('/accounts/otp-verify/')
        self.assertEqual(resp['Location'], '/accounts/login/')

    def test_otp_page_without_password_step_goes_to_login(self):
        self.assertEqual(self.client.get('/accounts/otp-verify/')['Location'], '/accounts/login/')

    def test_external_next_is_ignored(self):
        resp = self._login(qs='?next=https://evil.example/', next='https://evil.example/')
        self.assertEqual(resp['Location'], '/post-login/')


class BartingtonButtonTest(TestCase):
    """Tombol formulir Bartington hanya tampil Rabu & Jumat menurut WIT (UTC+9)."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('operator', password='rahasia12345')

    # ── logika hari (tanpa database) ────────────────────────────────────────
    def test_tampil_pada_rabu_dan_jumat_wit(self):
        self.assertTrue(bartington_form_open(datetime.datetime(2026, 11, 4, 3, 0, tzinfo=datetime.timezone.utc)))   # Rabu
        self.assertTrue(bartington_form_open(datetime.datetime(2026, 11, 6, 3, 0, tzinfo=datetime.timezone.utc)))   # Jumat

    def test_tidak_tampil_pada_hari_lain(self):
        for day in (1, 2, 3, 5, 7, 8):        # Sen, Sel, Kam, Sab, Min, Sen
            with self.subTest(day=day):
                self.assertFalse(bartington_form_open(
                    datetime.datetime(2026, 11, day, 3, 0, tzinfo=datetime.timezone.utc)))

    def test_patokan_hari_memakai_wit_bukan_utc(self):
        # Kamis 16:00 UTC == Jumat 01:00 WIT → tombol sudah tampil
        self.assertTrue(bartington_form_open(datetime.datetime(2026, 11, 5, 16, 0, tzinfo=datetime.timezone.utc)))
        # Rabu 16:00 UTC == Kamis 01:00 WIT → sudah tidak tampil
        self.assertFalse(bartington_form_open(datetime.datetime(2026, 11, 4, 16, 0, tzinfo=datetime.timezone.utc)))
        # Selasa 20:00 UTC == Rabu 05:00 WIT → tampil
        self.assertTrue(bartington_form_open(datetime.datetime(2026, 11, 3, 20, 0, tzinfo=datetime.timezone.utc)))

    # ── pemasangan di template dashboard ────────────────────────────────────
    @mock.patch('theme.views.bartington_form_open', return_value=True)
    def test_dashboard_menampilkan_tombol(self, _patched):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Formulir Bartington')
        self.assertContains(resp, reverse('observation_bartington'))

    @mock.patch('theme.views.bartington_form_open', return_value=False)
    def test_dashboard_menyembunyikan_tombol(self, _patched):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'Formulir Bartington')
        self.assertNotContains(resp, reverse('observation_bartington'))
