import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from .models import Hujan


def make_hujan(**kwargs):
    defaults = dict(
        tanggal=datetime.date(2024, 3, 1),
        hilman=12.5,
        obs=12.5,
        kategori='Sedang',
        petugas='Staff Ops',
    )
    defaults.update(kwargs)
    return Hujan.objects.create(**defaults)


class HujanModelTest(TestCase):
    def test_create(self):
        h = make_hujan()
        self.assertEqual(h.tanggal, datetime.date(2024, 3, 1))
        self.assertEqual(h.hilman, 12.5)

    def test_ordering_newest_first(self):
        make_hujan(tanggal=datetime.date(2024, 3, 1))
        make_hujan(tanggal=datetime.date(2024, 3, 2))
        dates = list(Hujan.objects.values_list('tanggal', flat=True))
        self.assertEqual(dates[0], datetime.date(2024, 3, 2))


class HujanViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('testuser', password='pass123')
        self.client.login(username='testuser', password='pass123')
        make_hujan()

    def test_daftar_hujan_get(self):
        resp = self.client.get(reverse('daftar_hujan'))
        self.assertEqual(resp.status_code, 200)

    def test_query_laporan_hujan_get(self):
        resp = self.client.get(reverse('query_laporan_hujan'))
        self.assertEqual(resp.status_code, 200)

    def test_query_laporan_hujan_with_date_range(self):
        resp = self.client.get(reverse('query_laporan_hujan'), {
            'start_date': '2024-01-01',
            'end_date': '2024-12-31',
        })
        self.assertEqual(resp.status_code, 200)

    def test_edit_hujan_get(self):
        h = make_hujan(tanggal=datetime.date(2024, 4, 1))
        resp = self.client.get(reverse('edit_hujan', args=[h.id]))
        self.assertEqual(resp.status_code, 200)

    def test_edit_hujan_post_updates_record(self):
        h = make_hujan(tanggal=datetime.date(2024, 5, 1))
        resp = self.client.post(reverse('edit_hujan', args=[h.id]), {
            'tanggal': '2024-05-01',
            'hilman': 20.0,
            'obs': 20.0,
            'kategori': 'Lebat',
            'petugas': 'Jambari',
        })
        self.assertIn(resp.status_code, [200, 302])
        h.refresh_from_db()
        self.assertEqual(float(h.hilman), 20.0)

    def test_edit_hujan_404_on_invalid_id(self):
        resp = self.client.get(reverse('edit_hujan', args=[9999]))
        self.assertEqual(resp.status_code, 404)

    def test_unauthenticated_daftar_accessible(self):
        self.client.logout()
        resp = self.client.get(reverse('daftar_hujan'))
        self.assertIn(resp.status_code, [200, 302, 403])
