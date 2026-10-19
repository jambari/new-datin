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


class EventBrowserViewsTest(TestCase):
    """Regresi: /repository/integrasi/ 500 (NameError: EventBrowser tidak diimpor)."""

    def setUp(self):
        from .models import EventBrowser
        self.user = User.objects.create_user('integrasi', password='pass123')
        self.client.force_login(self.user)
        self.ev = EventBrowser.objects.create(
            event_id='bmg2026abcd',
            origin_time=datetime.datetime(2026, 10, 1, 3, tzinfo=datetime.timezone.utc),
            magnitude=4.2, latitude=-2.5, longitude=140.7, depth_km=10)

    def test_list_and_detail_render(self):
        resp = self.client.get(reverse('event_browser_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'bmg2026abcd')
        resp = self.client.get(reverse('event_browser_detail', args=[self.ev.pk]))
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get(reverse('event_browser_edit', args=[self.ev.pk]))
        self.assertEqual(resp.status_code, 200)


class ComputeSeismicAvailabilityTest(TestCase):
    """Seismic availability comes from the SDS archive, not accelero samples."""

    def _qc(self, sta, cha, pct, loc='', net='IA', day=datetime.date(2026, 10, 13)):
        from qc_review.models import StationDailyQC
        StationDailyQC.objects.create(network=net, station=sta, location=loc, channel=cha,
                                      day=day, metrics={'availability_pct': pct})

    def _run(self, day='2026-10-13'):
        from io import StringIO
        from django.core.management import call_command
        call_command('compute_seismic_availability', date=day, stdout=StringIO())

    def _pct(self, sta, day=datetime.date(2026, 10, 13)):
        return DataAvailability.objects.get(station=sta, channel='SLINKTOOL', date=day).percentage

    def test_station_availability_ignores_accelerograph_channels(self):
        from repository.management.commands.compute_seismic_availability import station_availability
        rows = [('00', 'HHZ', {'availability_pct': 85.0}), ('00', 'HHN', {'availability_pct': 85.0}),
                ('00', 'HHE', {'availability_pct': 85.0}), ('', 'HNZ', {'availability_pct': 0.0})]
        self.assertEqual(station_availability(rows), 85.0)
        self.assertIsNone(station_availability([('', 'HNZ', {'availability_pct': 100.0})]))

    def test_best_group_wins(self):
        from repository.management.commands.compute_seismic_availability import station_availability
        rows = [('', 'BHZ', {'availability_pct': 100.0}), ('00', 'BHZ', {'availability_pct': 80.0})]
        self.assertEqual(station_availability(rows), 100.0)

    def test_writes_sds_value_and_zero_for_absent_station(self):
        for c in ('HHZ', 'HHN', 'HHE'):
            self._qc('WAMI', c, 85.05, loc='00')
        self._run()
        self.assertEqual(self._pct('WAMI'), 85.05)
        self.assertEqual(self._pct('DYPI'), 0.0)

    def test_day_not_posted_is_skipped(self):
        DataAvailability.objects.create(station='WAMI', channel='SLINKTOOL',
                                        date=datetime.date(2026, 10, 12), percentage=42.0)
        self._run('2026-10-12')
        self.assertEqual(self._pct('WAMI', datetime.date(2026, 10, 12)), 42.0)


@__import__('django').test.override_settings(WAVESIM_WORKER_TOKEN='tok')
class WaveSimulationTest(TestCase):
    """Queueing by staff and the worker claim/result/fail API."""

    def setUp(self):
        import tempfile
        from repository.models import GempaMemusak
        self.media = tempfile.mkdtemp()
        self.ev = GempaMemusak.objects.create(
            no=9001, tanggal_text='16 Oktober 2025', tanggal=datetime.date(2025, 10, 16),
            wilayah='Sarmi', latitude=-2.18, longitude=138.94, depth_km=16.0, magnitude=6.4,
            strike=149.15, dip=38.39, rake=70.37)
        self.user = User.objects.create_user('staf', password='x')
        self.auth = {'HTTP_AUTHORIZATION': 'Bearer tok'}

    def tearDown(self):
        import shutil
        shutil.rmtree(self.media, ignore_errors=True)

    def _queue(self):
        self.client.force_login(self.user)
        return self.client.post(reverse('gempa_merusak_wavesim', args=[self.ev.pk]))

    def _archive(self, names):
        import io, tarfile
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz') as tar:
            for name in names:
                data = b'png'
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        buf.seek(0)
        buf.name = 'assets.tar.gz'
        return buf

    def test_queue_once(self):
        from repository.models import WaveSimulation
        self._queue()
        self._queue()
        self.assertEqual(WaveSimulation.objects.filter(event=self.ev).count(), 1)

    def test_event_without_mechanism_is_refused(self):
        from repository.models import WaveSimulation
        self.ev.strike = None
        self.ev.save()
        self._queue()
        self.assertFalse(WaveSimulation.objects.exists())

    def test_claim_requires_token(self):
        r = self.client.post('/api/wavesim/claim/', HTTP_AUTHORIZATION='Bearer wrong')
        self.assertEqual(r.status_code, 401)

    def test_claim_and_result(self):
        import os
        from django.test import override_settings
        from repository.models import WaveSimulation
        self._queue()
        job = self.client.post('/api/wavesim/claim/', **self.auth).json()['job']
        self.assertEqual(job['event']['magnitude'], 6.4)
        self.assertEqual(job['event']['origin'], '2025-10-16T00:00:00')
        self.assertIsNone(self.client.post('/api/wavesim/claim/', **self.auth).json()['job'])

        with override_settings(MEDIA_ROOT=self.media):
            r = self.client.post(f"/api/wavesim/{job['id']}/result/", **self.auth, data={
                'archive': self._archive(['pgv.png', 'frames/f000.png', '../evil.png', 'x.sh']),
                'result': '{"bounds": [[-3, 137], [-1, 140]], "frame_times": [0.0]}'})
            self.assertEqual(r.json()['files'], 2)
            sim = WaveSimulation.objects.get(pk=job['id'])
            self.assertEqual(sim.status, 'done')
            self.assertTrue(os.path.exists(os.path.join(self.media, sim.asset_dir, 'frames', 'f000.png')))
            self.assertFalse(os.path.exists(os.path.join(self.media, 'wavesim', 'evil.png')))

            page = self.client.get(reverse('public_gempa_merusak_detail', args=[self.ev.pk]),
                                   HTTP_HOST='localhost')
            self.assertContains(page, 'Simulasi Penjalaran Gelombang')
            self.assertContains(page, f'/media/wavesim/{sim.pk}/frames/')

    def test_fail(self):
        from repository.models import WaveSimulation
        self._queue()
        job = self.client.post('/api/wavesim/claim/', **self.auth).json()['job']
        self.client.post(f"/api/wavesim/{job['id']}/fail/", **self.auth, data={'log': 'boom'})
        sim = WaveSimulation.objects.get(pk=job['id'])
        self.assertEqual((sim.status, sim.log), ('failed', 'boom'))


class ShakemapLookupTest(TestCase):
    """Record ShakemapEvent lama ber-id '<WIB>_mag_lat_lon_<WIB>' harus tetap ditemukan."""

    def setUp(self):
        import datetime as _d
        from .models import ShakemapEvent
        utc = _d.timezone.utc
        self.legacy = ShakemapEvent.objects.create(
            event_id="20260114064812_32_-3700_133590_20260114064812", latitude=-3.7, longitude=133.59,
            magnitude=3.2, depth=10, event_time=_d.datetime(2026, 1, 14, 6, 48, 12, tzinfo=utc),
            location_string="KAIMANA", shakemap_image="shakemaps/legacy.jpg")
        self.new = ShakemapEvent.objects.create(
            event_id="20260517142319", latitude=-2.5, longitude=140.7, magnitude=3.6, depth=10,
            event_time=_d.datetime(2026, 5, 17, 7, 23, 19, tzinfo=utc), location_string="JAYAPURA",
            shakemap_image="shakemaps/20260517142319.mmi.jpg")

    def test_find_by_new_and_legacy_id_with_tolerance(self):
        from .shakemap_lookup import find_shakemap_event, wib_id_to_utc
        import datetime as _d
        self.assertEqual(find_shakemap_event("20260517142319"), self.new)
        self.assertEqual(find_shakemap_event("20260114064812"), self.legacy)
        self.assertEqual(find_shakemap_event("20260114064814"), self.legacy)  # origin beda 2 detik
        self.assertIsNone(find_shakemap_event("20260114064830"))
        self.assertEqual(wib_id_to_utc("20260114064812"), _d.datetime(2026, 1, 13, 23, 48, 12, tzinfo=_d.timezone.utc))

    def test_public_detail_shows_intensity_for_legacy_event(self):
        import datetime as _d
        from .models import FeltEarthquake
        fe = FeltEarthquake.objects.create(
            event_datetime=_d.datetime(2026, 1, 13, 23, 48, 12, tzinfo=_d.timezone.utc), latitude=-3.7,
            longitude=133.59, magnitude=3.2, depth_km=10, wilayah="KAIMANA")
        r = self.client.get(f"/shakemap/{fe.pk}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["shk_event"], self.legacy)
        self.assertContains(r, "/media/shakemaps/legacy.jpg")


class EventBrowserPetugasTest(TestCase):
    """Event browser memakai petugas tersimpan di event QC dan menyaring per pegawai."""

    def test_stored_petugas_and_pegawai_filter(self):
        import datetime as _d, json
        from django.contrib.auth import get_user_model
        from jadwal.models import Pegawai
        from qc_review.models import Event, QCRun
        a = Pegawai.objects.create(nama="ANAS", nip="1", pangkat="-", jabatan="-")
        b = Pegawai.objects.create(nama="JAMBARI", nip="2", pangkat="-", jabatan="-")
        today = _d.date.today()
        t = _d.datetime.combine(today, _d.time(3), tzinfo=_d.timezone.utc)
        e1 = Event.objects.create(public_id="x1", origin_time=t, latitude=-2.5, longitude=140.7, depth_km=10, magnitude=3.0)
        e2 = Event.objects.create(public_id="x2", origin_time=t + _d.timedelta(hours=1), latitude=-2.5, longitude=140.7, depth_km=10, magnitude=3.1)
        for e in (e1, e2):
            QCRun.objects.create(event=e, run_number=1)
        e1.petugas.set([a, b]); e2.petugas.set([b])
        self.client.force_login(get_user_model().objects.create_user("u", password="x"))
        r = self.client.get("/repository/event-browser/")
        data = {d["event_id"]: d["petugas"] for d in json.loads(r.context["qc_map_data"])}
        self.assertEqual(data, {"x1": "ANAS, JAMBARI", "x2": "JAMBARI"})
        r = self.client.get(f"/repository/event-browser/?pegawai={a.pk}")
        self.assertEqual([d["event_id"] for d in json.loads(r.context["qc_map_data"])], ["x1"])


from unittest import mock  # noqa: E402


class EventBrowserGmtMapTest(TestCase):
    def setUp(self):
        import tempfile, shutil
        from django.contrib.auth import get_user_model
        self.client.force_login(get_user_model().objects.create_user('gmt', password='x'))
        self.media = tempfile.mkdtemp(prefix='gmt-media-')
        self.addCleanup(shutil.rmtree, self.media, True)

    def _fake_run(self, calls):
        import json as _json
        from pathlib import Path as _Path
        def run(cmd, **kw):
            calls.append(_json.loads(_Path(cmd[2]).read_text()))
            _Path(cmd[3]).write_bytes(b'\x89PNG fake')
            return mock.Mock(returncode=0, stderr='')
        return run

    def test_renders_and_caches(self):
        from django.test import override_settings
        calls = []
        with override_settings(MEDIA_ROOT=self.media), \
                mock.patch('subprocess.run', side_effect=self._fake_run(calls)):
            url = '/repository/event-browser/gmt-map/?start=2026-09-01&end=2026-09-30'
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r['Content-Type'], 'image/png')
            self.assertTrue(r['Content-Disposition'].startswith('inline;'))
            self.assertEqual(self.client.get(url + '&download=1')['Content-Disposition'].split(';')[0], 'attachment')
        self.assertEqual(len(calls), 1)                       # kedua kalinya dari cache
        cfg = calls[0]
        self.assertEqual(cfg['region'], [129.0, 146.0, -10.0, 2.0])
        self.assertIn('01 SEPTEMBER 2026 - 30 SEPTEMBER 2026', cfg['subtitle'])
        calls.clear()
        with override_settings(MEDIA_ROOT=self.media), \
                mock.patch('subprocess.run', side_effect=self._fake_run(calls)):
            self.client.get('/repository/event-browser/gmt-map/?start=2026-08-01&end=2026-08-31')
        self.assertIn('01 AGUSTUS 2026 - 31 AGUSTUS 2026', calls[0]['subtitle'])
        self.assertTrue(cfg['faults'].endswith('indofaults.js'))

    def test_failure_returns_503(self):
        from django.test import override_settings
        with override_settings(MEDIA_ROOT=self.media), \
                mock.patch('subprocess.run', return_value=mock.Mock(returncode=1, stderr='boom')):
            r = self.client.get('/repository/event-browser/gmt-map/?start=2026-08-01&end=2026-08-02')
        self.assertEqual(r.status_code, 503)

    def test_tab_present(self):
        r = self.client.get('/repository/event-browser/?start=2026-09-01&end=2026-09-30')
        self.assertContains(r, 'Peta Seismisitas (GMT)')
        self.assertContains(r, '/repository/event-browser/gmt-map/')
        self.assertContains(r, '<option value="gmtrelief" selected>')
        self.assertContains(r, 'baseLayer = gmtReliefLayer().addTo(mapInstance)')
        self.assertContains(r, 'tiles/gmt_relief/{z}/{x}/{y}.webp')
