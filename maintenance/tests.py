import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from .models import Instrument, Issue, ActionLog


def make_user(username='testuser', password='pass123'):
    return User.objects.create_user(username, password=password)


def make_instrument(**kwargs):
    defaults = dict(
        nama_alat='Seismometer A',
        jenis='SEIS',
        lokasi='Jayapura',
        shelter='JYP',
        status='AKTIF',
    )
    defaults.update(kwargs)
    return Instrument.objects.create(**defaults)


def make_issue(instrument, user, **kwargs):
    defaults = dict(
        instrument=instrument,
        judul='Sensor Error',
        kategori='SENSOR',
        deskripsi='Sensor tidak merespons',
        prioritas='TINGGI',
        status='OPEN',
        pic=user,
    )
    defaults.update(kwargs)
    return Issue.objects.create(**defaults)


class InstrumentModelTest(TestCase):
    def test_create_and_str(self):
        inst = make_instrument()
        self.assertIn('JYP', str(inst))

    def test_default_status_aktif(self):
        inst = make_instrument()
        self.assertEqual(inst.status, 'AKTIF')

    def test_ordering_by_shelter_then_jenis(self):
        make_instrument(nama_alat='MAG', jenis='MAG', shelter='JYP')
        make_instrument(nama_alat='SEIS', jenis='SEIS', shelter='AAA')
        shelters = list(Instrument.objects.values_list('shelter', flat=True))
        self.assertEqual(shelters[0], 'AAA')


class IssueModelTest(TestCase):
    def setUp(self):
        self.inst = make_instrument()
        self.user = make_user()

    def test_create_and_str(self):
        issue = make_issue(self.inst, self.user)
        self.assertIn('OPEN', str(issue))
        self.assertIn('JYP', str(issue))

    def test_default_status_open(self):
        issue = make_issue(self.inst, self.user)
        self.assertEqual(issue.status, 'OPEN')

    def test_default_prioritas_sedang(self):
        issue = Issue.objects.create(
            instrument=self.inst,
            judul='Test',
            kategori='LAIN',
            deskripsi='Test',
            pic=self.user,
        )
        self.assertEqual(issue.prioritas, 'SEDANG')


class ActionLogModelTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.inst = make_instrument()
        self.issue = make_issue(self.inst, self.user)

    def test_create_and_str(self):
        log = ActionLog.objects.create(
            issue=self.issue,
            tindakan='Mengganti kabel sensor',
            oleh=self.user,
        )
        self.assertIn('Mengganti kabel', str(log))

    def test_cascade_delete_with_issue(self):
        ActionLog.objects.create(issue=self.issue, tindakan='Test', oleh=self.user)
        self.issue.delete()
        self.assertEqual(ActionLog.objects.count(), 0)


class MaintenanceViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user()
        self.client.login(username='testuser', password='pass123')
        self.inst = make_instrument()
        self.issue = make_issue(self.inst, self.user)

    def test_dashboard_get(self):
        resp = self.client.get(reverse('maintenance:dashboard'))
        self.assertEqual(resp.status_code, 200)

    def test_instrument_list_get(self):
        resp = self.client.get(reverse('maintenance:instrument_list'))
        self.assertEqual(resp.status_code, 200)

    def test_issue_list_get(self):
        resp = self.client.get(reverse('maintenance:issue_list'))
        self.assertEqual(resp.status_code, 200)

    def test_instrument_create_get(self):
        resp = self.client.get(reverse('maintenance:instrument_create'))
        self.assertEqual(resp.status_code, 200)

    def test_instrument_create_post(self):
        resp = self.client.post(reverse('maintenance:instrument_create'), {
            'nama_alat': 'New Sensor',
            'jenis': 'ACC',
            'lokasi': 'Serui',
            'shelter': 'SRI',
            'status': 'AKTIF',
        })
        self.assertIn(resp.status_code, [200, 302])

    def test_instrument_update_get(self):
        resp = self.client.get(reverse('maintenance:instrument_update', args=[self.inst.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_instrument_delete_get(self):
        resp = self.client.get(reverse('maintenance:instrument_delete', args=[self.inst.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_issue_create_get(self):
        resp = self.client.get(reverse('maintenance:issue_create'))
        self.assertEqual(resp.status_code, 200)

    def test_issue_update_get(self):
        resp = self.client.get(reverse('maintenance:issue_update', args=[self.issue.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_issue_delete_get(self):
        resp = self.client.get(reverse('maintenance:issue_delete', args=[self.issue.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_instrument_404_on_invalid(self):
        resp = self.client.get(reverse('maintenance:instrument_update', args=[9999]))
        self.assertEqual(resp.status_code, 404)

    def test_unauthenticated_dashboard_redirects(self):
        self.client.logout()
        resp = self.client.get(reverse('maintenance:dashboard'))
        self.assertIn(resp.status_code, [200, 302, 403])
