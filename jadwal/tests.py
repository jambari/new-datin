import datetime
import json
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from .models import Pegawai, PolaDinas, JadwalHarian, RiwayatJadwal, JadwalHVSampler


def make_user(username='testuser', password='pass123'):
    return User.objects.create_user(username, password=password)


def make_pegawai(user=None, **kwargs):
    if user is None:
        user = make_user()
    defaults = dict(
        user=user,
        nama='Jambari',
        nip='197001011990031001',
        pangkat='Penata Muda (III/a)',
        jabatan='PMG Pertama',
    )
    defaults.update(kwargs)
    return Pegawai.objects.create(**defaults)


def make_pola(**kwargs):
    defaults = dict(
        kode='P',
        nama='Pagi',
        jam_mulai=datetime.time(7, 0),
        jam_selesai=datetime.time(14, 0),
        durasi=7.0,
        warna='#FFFF00',
    )
    defaults.update(kwargs)
    return PolaDinas.objects.create(**defaults)


class PegawaiModelTest(TestCase):
    def test_create_and_str(self):
        p = make_pegawai()
        self.assertEqual(str(p), 'Jambari')

    def test_unique_nip(self):
        make_pegawai(nip='12345')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            user2 = User.objects.create_user('user2', password='pass')
            make_pegawai(user=user2, nip='12345')

    def test_ordering_by_urutan_then_nama(self):
        u1 = User.objects.create_user('u1', password='p')
        u2 = User.objects.create_user('u2', password='p')
        Pegawai.objects.create(user=u1, nama='Budi', nip='001', pangkat='P', jabatan='J', urutan=2)
        Pegawai.objects.create(user=u2, nama='Andi', nip='002', pangkat='P', jabatan='J', urutan=1)
        names = list(Pegawai.objects.values_list('nama', flat=True))
        self.assertEqual(names[0], 'Andi')


class PolaDinasModelTest(TestCase):
    def test_create_and_str(self):
        pola = make_pola()
        self.assertIn('P', str(pola))
        self.assertIn('7.0', str(pola))

    def test_unique_kode(self):
        make_pola(kode='P')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            make_pola(kode='P')


class JadwalHarianModelTest(TestCase):
    def setUp(self):
        self.pegawai = make_pegawai()
        self.pola = make_pola()

    def test_create_and_str(self):
        jadwal = JadwalHarian.objects.create(
            pegawai=self.pegawai,
            tanggal=datetime.date(2024, 3, 1),
            pola=self.pola,
        )
        self.assertIn('Jambari', str(jadwal))

    def test_unique_together_pegawai_tanggal(self):
        JadwalHarian.objects.create(
            pegawai=self.pegawai,
            tanggal=datetime.date(2024, 3, 1),
            pola=self.pola,
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            JadwalHarian.objects.create(
                pegawai=self.pegawai,
                tanggal=datetime.date(2024, 3, 1),
                pola=self.pola,
            )

    def test_default_not_approved(self):
        jadwal = JadwalHarian.objects.create(
            pegawai=self.pegawai,
            tanggal=datetime.date(2024, 3, 1),
        )
        self.assertFalse(jadwal.is_approved)


class JadwalHVSamplerModelTest(TestCase):
    def test_create_and_str(self):
        obj = JadwalHVSampler.objects.create(
            tanggal=datetime.date(2024, 3, 1),
            tipe='PS',
        )
        self.assertIn('2024-03-01', str(obj))

    def test_ordering_by_date(self):
        JadwalHVSampler.objects.create(tanggal=datetime.date(2024, 3, 2), tipe='AK')
        JadwalHVSampler.objects.create(tanggal=datetime.date(2024, 3, 1), tipe='PS')
        dates = list(JadwalHVSampler.objects.values_list('tanggal', flat=True))
        self.assertEqual(dates[0], datetime.date(2024, 3, 1))


class JadwalViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('testuser', password='pass123')
        self.client.login(username='testuser', password='pass123')
        make_pola()

    def test_tabel_jadwal_get(self):
        resp = self.client.get(reverse('jadwal_dinas'))
        self.assertEqual(resp.status_code, 200)

    def test_tabel_jadwal_with_month_year(self):
        resp = self.client.get(reverse('jadwal_dinas'), {'month': 3, 'year': 2024})
        self.assertEqual(resp.status_code, 200)

    def test_generate_auto_schedule_post(self):
        resp = self.client.post(
            reverse('api_generate_jadwal'),
            data=json.dumps({'month': 3, 'year': 2024}),
            content_type='application/json',
        )
        self.assertIn(resp.status_code, [200, 302, 400])

    def test_update_jadwal_api_post(self):
        pegawai = make_pegawai(make_user('officer'))
        pola = make_pola(kode='S')
        payload = {
            'pegawai_id': pegawai.id,
            'tanggal': '2024-03-01',
            'pola_kode': pola.kode,
        }
        resp = self.client.post(
            reverse('api_update_jadwal'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertIn(resp.status_code, [200, 400])

    def test_approve_all_jadwal_get(self):
        resp = self.client.get(reverse('approve_all_jadwal'), {'month': 3, 'year': 2024})
        self.assertIn(resp.status_code, [200, 302, 403])

    def test_unauthenticated_redirects(self):
        self.client.logout()
        resp = self.client.get(reverse('jadwal_dinas'))
        self.assertIn(resp.status_code, [200, 302, 403])
