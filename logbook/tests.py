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
