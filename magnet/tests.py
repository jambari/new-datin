import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from .models import MagneticObservation, Precursor, MagnetDataAvailability


def make_observation(**kwargs):
    defaults = dict(
        observation_date=datetime.date(2024, 3, 1),
        observer='Jambari',
        session='Pagi',
    )
    defaults.update(kwargs)
    return MagneticObservation.objects.create(**defaults)


class MagneticObservationModelTest(TestCase):
    def test_create_and_str(self):
        obs = make_observation()
        self.assertIn('2024-03-01', str(obs))
        self.assertIn('Jambari', str(obs))

    def test_is_bartington_false_without_readings(self):
        obs = make_observation()
        self.assertFalse(obs.is_bartington)

    def test_is_bartington_true_with_deg_readings(self):
        obs = make_observation(deklinasi_readings={
            'WU': {'deg': 10, 'min': 30, 'sec': 0},
        })
        self.assertTrue(obs.is_bartington)

    def test_derived_components_calculated_on_save(self):
        obs = make_observation(
            declination=1.0,
            inclination=-30.0,
            total_intensity=45000.0,
        )
        obs.refresh_from_db()
        self.assertIsNotNone(obs.horizontal_intensity)
        self.assertIsNotNone(obs.vertical_intensity)
        self.assertIsNotNone(obs.north_component)
        self.assertIsNotNone(obs.east_component)

    def test_bartington_full_calculation(self):
        obs = make_observation(
            deklinasi_readings={
                'WU': {'deg': 181, 'min': 0, 'sec': 0},
                'ED': {'deg': 181, 'min': 0, 'sec': 0},
                'WD': {'deg': 181, 'min': 0, 'sec': 0},
                'EU': {'deg': 181, 'min': 0, 'sec': 0},
            },
            inklinasi_readings={
                'NU': {'deg': 150, 'min': 0, 'sec': 0, 'ftotal': 45000},
                'SD': {'deg': 300, 'min': 0, 'sec': 0, 'ftotal': 45000},
                'ND': {'deg': 210, 'min': 0, 'sec': 0, 'ftotal': 45000},
                'SU': {'deg': 60, 'min': 0, 'sec': 0, 'ftotal': 45000},
            },
        )
        obs.refresh_from_db()
        self.assertIsNotNone(obs.declination)
        self.assertIsNotNone(obs.inclination)
        self.assertEqual(float(obs.total_intensity), 45000.0)


class PrecursorModelTest(TestCase):
    def test_create_and_str(self):
        p = Precursor.objects.create(
            anomaly_timestamp=datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc),
            predicted_start_date=datetime.date(2024, 1, 10),
            predicted_end_date=datetime.date(2024, 1, 20),
            predicted_magnitude=6.0,
            location_description='Papua Tengah',
        )
        self.assertIn('Papua Tengah', str(p))

    def test_default_not_validated(self):
        p = Precursor.objects.create(
            anomaly_timestamp=datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc),
            predicted_start_date=datetime.date(2024, 1, 10),
            predicted_end_date=datetime.date(2024, 1, 20),
            predicted_magnitude=6.0,
            location_description='Test',
        )
        self.assertFalse(p.is_validated)


class MagnetDataAvailabilityModelTest(TestCase):
    def test_create_and_str(self):
        obj = MagnetDataAvailability.objects.create(
            station='JYP_P',
            date=datetime.date(2024, 3, 1),
            percentage=98.5,
        )
        self.assertIn('JYP_P', str(obj))

    def test_unique_together_constraint(self):
        MagnetDataAvailability.objects.create(
            station='JYP_P', date=datetime.date(2024, 3, 1), percentage=98.5
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            MagnetDataAvailability.objects.create(
                station='JYP_P', date=datetime.date(2024, 3, 1), percentage=50.0
            )


class MagnetViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('testuser', password='pass123')
        self.client.login(username='testuser', password='pass123')

    def test_observation_form_get(self):
        resp = self.client.get(reverse('observation_form'))
        self.assertEqual(resp.status_code, 200)

    def test_observation_bartington_form_get(self):
        resp = self.client.get(reverse('observation_bartington'))
        self.assertEqual(resp.status_code, 200)

    def test_observation_list_get(self):
        resp = self.client.get(reverse('observation_list'))
        self.assertEqual(resp.status_code, 200)

    def test_precursor_list_get(self):
        resp = self.client.get(reverse('precursor_list'))
        self.assertEqual(resp.status_code, 200)

    def test_magnet_availability_query_get(self):
        resp = self.client.get(reverse('magnet_availability_query'))
        self.assertEqual(resp.status_code, 200)

    def test_observation_detail_404_on_invalid(self):
        resp = self.client.get(reverse('observation_detail', args=[9999]))
        self.assertEqual(resp.status_code, 404)

    def test_precursor_detail_404_on_invalid(self):
        resp = self.client.get(reverse('precursor_detail', args=[9999]))
        self.assertEqual(resp.status_code, 404)

    def test_unauthenticated_redirects(self):
        self.client.logout()
        resp = self.client.get(reverse('observation_form'))
        self.assertIn(resp.status_code, [302, 403])

    def test_update_magnet_availability_post(self):
        payload = {'station': 'JYP_P', 'date': '2024-03-01', 'value': 99.0}
        resp = self.client.post(
            reverse('update_magnet_availability'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertIn(resp.status_code, [200, 201])


import json


# ── Indeks magnetbumi K & A (scraping harian) ────────────────────────────────

import hashlib
import shutil
import tempfile
from unittest import mock

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from .models import FmiIndicesImage

# PNG minimal (header valid) — cukup untuk pengecekan magic bytes di command.
TINY_PNG = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00'
    b'\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00'
    b'\x00\x00IEND\xaeB`\x82'
)

_CMD = 'magnet.management.commands.fetch_fmi_indices'


class FmiIndicesImageModelTest(TestCase):
    def setUp(self):
        # Jangan tulis ke MEDIA_ROOT sungguhan saat test.
        self.media_root = tempfile.mkdtemp(prefix='fmi-test-media-')
        self.addCleanup(shutil.rmtree, self.media_root, True)
        ctx = override_settings(MEDIA_ROOT=self.media_root)
        ctx.enable()
        self.addCleanup(ctx.disable)

    def test_create_and_str(self):
        obj = FmiIndicesImage.objects.create(
            jenis=FmiIndicesImage.K,
            tanggal=datetime.date(2026, 10, 3),
            image=SimpleUploadedFile('k.png', TINY_PNG, content_type='image/png'),
        )
        self.assertIn('K', str(obj))
        self.assertIn('2026-10-03', str(obj))
        self.assertEqual(obj.jenis_label, 'K Indices')

    def test_unique_per_jenis_and_tanggal(self):
        from django.db import IntegrityError

        FmiIndicesImage.objects.create(
            jenis=FmiIndicesImage.K, tanggal=datetime.date(2026, 10, 3),
            image=SimpleUploadedFile('a.png', TINY_PNG),
        )
        with self.assertRaises(IntegrityError):
            FmiIndicesImage.objects.create(
                jenis=FmiIndicesImage.K, tanggal=datetime.date(2026, 10, 3),
                image=SimpleUploadedFile('b.png', TINY_PNG),
            )

    def test_k_and_a_can_share_the_same_date(self):
        for jenis in (FmiIndicesImage.K, FmiIndicesImage.A):
            FmiIndicesImage.objects.create(
                jenis=jenis, tanggal=datetime.date(2026, 10, 3),
                image=SimpleUploadedFile(f'{jenis}.png', TINY_PNG),
            )
        self.assertEqual(FmiIndicesImage.objects.filter(tanggal=datetime.date(2026, 10, 3)).count(), 2)

    def test_filename_property(self):
        obj = FmiIndicesImage(jenis='A', tanggal=datetime.date(2026, 10, 3))
        self.assertEqual(obj.filename, 'FMI-A-Indices-JYP-20261003.png')


class FmiIndicesFetchCommandTest(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix='fmi-test-media-')
        self.addCleanup(shutil.rmtree, self.media_root, True)
        ctx = override_settings(MEDIA_ROOT=self.media_root)
        ctx.enable()
        self.addCleanup(ctx.disable)

    @staticmethod
    def _response(content=TINY_PNG, status=200, headers=None):
        resp = mock.Mock()
        resp.status_code = status
        resp.content = content
        resp.headers = headers if headers is not None else {'ETag': '"etag-1"', 'Content-Type': 'image/png'}
        return resp

    def test_fetch_stores_one_record_per_jenis(self):
        with mock.patch(f'{_CMD}.requests.get', return_value=self._response()):
            call_command('fetch_fmi_indices', '--date', '2026-10-03', '--no-telegram')

        self.assertEqual(FmiIndicesImage.objects.count(), 2)
        expected_sha = hashlib.sha256(TINY_PNG).hexdigest()
        for rec in FmiIndicesImage.objects.all():
            self.assertEqual(rec.tanggal, datetime.date(2026, 10, 3))
            self.assertEqual(rec.size_bytes, len(TINY_PNG))
            self.assertEqual(rec.sha256, expected_sha)
            self.assertTrue(rec.image.storage.exists(rec.image.name))
            self.assertIsNone(rec.telegram_sent_at)  # --no-telegram

    def test_rerun_same_day_is_idempotent(self):
        with mock.patch(f'{_CMD}.requests.get', return_value=self._response()):
            call_command('fetch_fmi_indices', '--date', '2026-10-03', '--no-telegram')
            call_command('fetch_fmi_indices', '--date', '2026-10-03', '--no-telegram')

        self.assertEqual(FmiIndicesImage.objects.count(), 2)
        names = sorted(FmiIndicesImage.objects.values_list('image', flat=True))
        self.assertEqual(len(set(names)), 2)  # tidak ada file bersuffix

    def test_single_jenis_flag(self):
        with mock.patch(f'{_CMD}.requests.get', return_value=self._response()):
            call_command('fetch_fmi_indices', '--date', '2026-10-03', '--jenis', 'K', '--no-telegram')
        self.assertEqual(FmiIndicesImage.objects.count(), 1)
        self.assertEqual(FmiIndicesImage.objects.first().jenis, 'K')

    def test_non_png_response_is_rejected(self):
        bad = self._response(content=b'<html>not an image</html>', headers={'Content-Type': 'text/html'})
        with mock.patch(f'{_CMD}.requests.get', return_value=bad), \
             mock.patch(f'{_CMD}.time.sleep', return_value=None):
            with self.assertRaises(CommandError):
                call_command('fetch_fmi_indices', '--date', '2026-10-03', '--no-telegram')
        self.assertEqual(FmiIndicesImage.objects.count(), 0)

    def test_telegram_failure_does_not_block_storage(self):
        """Token kosong => pengiriman dilewati, tetapi citra tetap tersimpan."""
        with override_settings(TELEGRAM_BOT_TOKEN='', TELEGRAM_CHAT_ID=''), \
             mock.patch(f'{_CMD}.requests.get', return_value=self._response()):
            call_command('fetch_fmi_indices', '--date', '2026-10-03')
        self.assertEqual(FmiIndicesImage.objects.count(), 2)
        self.assertIsNone(FmiIndicesImage.objects.first().telegram_sent_at)


class FmiIndicesViewTest(TestCase):
    def setUp(self):
        # Jangan tulis ke MEDIA_ROOT sungguhan saat test.
        self.media_root = tempfile.mkdtemp(prefix='fmi-test-media-')
        self.addCleanup(shutil.rmtree, self.media_root, True)
        ctx = override_settings(MEDIA_ROOT=self.media_root)
        ctx.enable()
        self.addCleanup(ctx.disable)

    @staticmethod
    def _make(jenis, tanggal=datetime.date(2026, 10, 3)):
        """Buat record dengan nama file deterministik seperti hasil command."""
        obj = FmiIndicesImage(jenis=jenis, tanggal=tanggal)
        obj.image.save(obj.filename, ContentFile(TINY_PNG), save=False)
        obj.size_bytes = len(TINY_PNG)
        obj.sha256 = hashlib.sha256(TINY_PNG).hexdigest()
        obj.save()
        return obj

    def test_list_get(self):
        resp = self.client.get(reverse('fmi_indices_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Indeks K')

    def test_list_shows_stored_images(self):
        self._make(FmiIndicesImage.K)
        self._make(FmiIndicesImage.A)
        resp = self.client.get(reverse('fmi_indices_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'FMI-K-Indices-JYP-20261003.png')
        self.assertContains(resp, 'FMI-A-Indices-JYP-20261003.png')

    def test_list_empty_state(self):
        resp = self.client.get(reverse('fmi_indices_list'))
        self.assertContains(resp, 'Belum ada citra indeks')

    def test_filter_by_jenis(self):
        self._make(FmiIndicesImage.K)
        resp = self.client.get(reverse('fmi_indices_list'), {'jenis': 'A'})
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'FMI-K-Indices-JYP-20261003.png')

    def test_post_fetch_does_not_error_when_broker_unavailable(self):
        with mock.patch('magnet.tasks.fetch_fmi_indices_task.delay', side_effect=RuntimeError('broker down')):
            resp = self.client.post(reverse('fmi_indices_list'), {'action': 'fetch'}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Gagal menjadwalkan job')


class FmiIndicesPublicPageTest(TestCase):
    """Halaman publik indeks K & A + /magnetbumi/ + submenu navbar landing."""

    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix='fmi-test-media-')
        self.addCleanup(shutil.rmtree, self.media_root, True)
        ctx = override_settings(MEDIA_ROOT=self.media_root)
        ctx.enable()
        self.addCleanup(ctx.disable)

    @staticmethod
    def _make(jenis, tanggal=datetime.date(2026, 10, 3)):
        obj = FmiIndicesImage(jenis=jenis, tanggal=tanggal)
        obj.image.save(obj.filename, ContentFile(TINY_PNG), save=False)
        obj.size_bytes = len(TINY_PNG)
        obj.sha256 = hashlib.sha256(TINY_PNG).hexdigest()
        obj.save()
        return obj

    # ── halaman khusus indeks K & A ──────────────────────────────────────────

    def test_indices_page_shows_latest_pair(self):
        self._make(FmiIndicesImage.K)
        self._make(FmiIndicesImage.A)

        resp = self.client.get(reverse('public_magnetbumi_indices'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'FMI-K-Indices-JYP-20261003.png')
        self.assertContains(resp, 'FMI-A-Indices-JYP-20261003.png')
        self.assertContains(resp, 'K Indices')
        self.assertContains(resp, 'A Indices')

    def test_indices_page_shows_only_latest_date(self):
        self._make(FmiIndicesImage.K, tanggal=datetime.date(2026, 10, 3))
        self._make(FmiIndicesImage.A, tanggal=datetime.date(2026, 10, 3))
        self._make(FmiIndicesImage.K, tanggal=datetime.date(2026, 10, 2))
        self._make(FmiIndicesImage.A, tanggal=datetime.date(2026, 10, 2))

        resp = self.client.get(reverse('public_magnetbumi_indices'))
        self.assertContains(resp, 'FMI-K-Indices-JYP-20261003.png')
        self.assertNotContains(resp, 'FMI-K-Indices-JYP-20261002.png')

    def test_indices_page_empty_state_without_data(self):
        resp = self.client.get(reverse('public_magnetbumi_indices'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Citra indeks K &amp; A belum tersedia')

    def test_indices_page_partial_pair_does_not_break(self):
        """Hanya citra K tersimpan — halaman tetap tampil."""
        self._make(FmiIndicesImage.K)
        resp = self.client.get(reverse('public_magnetbumi_indices'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Citra A belum tersedia')

    def test_indices_page_has_no_magnetbumi_charts(self):
        """Halaman indeks tidak boleh memuat chart 7 komponen."""
        self._make(FmiIndicesImage.K)
        resp = self.client.get(reverse('public_magnetbumi_indices'))
        self.assertNotContains(resp, 'chart-grid')
        self.assertNotContains(resp, 'chart-D')

    def test_indices_page_header_css_matches_other_public_pages(self):
        """Halaman ini merender <header id="site-header"> sendiri.

        Halaman publik lain memasangkannya dengan CSS `#site-header {
        position: fixed; ... }` sehingga header bawaan base.html
        (_landing_header.html) menumpuk di posisi yang sama — tampak satu header.
        Tanpa CSS itu, keduanya tersusun vertikal dan header terlihat DOBEL.
        """
        resp = self.client.get(reverse('public_magnetbumi_indices'))
        self.assertContains(resp, '<header id="site-header"')
        self.assertContains(resp, 'position: fixed; top: 0; left: 0; right: 0; z-index: 1000;')
        self.assertContains(resp, '.header-inner')

    # ── /magnetbumi/ tetap 7 komponen, tanpa citra indeks ────────────────────

    def test_magnetbumi_page_has_seven_component_charts(self):
        resp = self.client.get(reverse('public_magnetbumi'))
        self.assertEqual(resp.status_code, 200)
        for canvas in ['chart-D', 'chart-I', 'chart-F', 'chart-H', 'chart-Z', 'chart-X', 'chart-Y']:
            self.assertContains(resp, canvas)

    def test_magnetbumi_page_has_no_index_images(self):
        """Citra K & A tidak lagi ditampilkan di /magnetbumi/ (terpisah)."""
        self._make(FmiIndicesImage.K)
        self._make(FmiIndicesImage.A)

        resp = self.client.get(reverse('public_magnetbumi'))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'id="indeks-k-a"')
        self.assertNotContains(resp, 'FMI-K-Indices-JYP-20261003.png')
        self.assertNotContains(resp, 'FMI-A-Indices-JYP-20261003.png')

    # ── navbar ───────────────────────────────────────────────────────────────

    def test_landing_navbar_links_to_separate_pages(self):
        resp = self.client.get(reverse('landing'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Absolut Magnetik')
        self.assertContains(resp, 'K dan A Indeks')
        # masing-masing menuju halaman sendiri, bukan anchor di halaman yang sama
        self.assertContains(resp, 'href="/magnetbumi/"')
        self.assertContains(resp, 'href="/magnetbumi/indeks-k-a/"')
        self.assertNotContains(resp, '/magnetbumi/#indeks-k-a')


# ── Notifikasi Telegram ──────────────────────────────────────────────────────
from unittest import mock

from django.test import override_settings


@override_settings(TELEGRAM_BOT_TOKEN='tok-123', TELEGRAM_CHAT_ID='-100123')
class BartingtonTelegramNotifyTest(TestCase):
    """Observasi absolut Bartington baru dikabarkan ke Telegram."""

    READINGS = {'WU': {'deg': 10, 'min': 30, 'sec': 0}}

    def _create(self, **kwargs):
        with mock.patch('theme.telegram.requests.post') as post:
            post.return_value = mock.Mock(status_code=200, text='')
            with self.captureOnCommitCallbacks(execute=True):
                obs = make_observation(**kwargs)
        return obs, post

    def test_bartington_record_is_sent(self):
        obs, post = self._create(
            observer='Jambari', session='Pagi',
            deklinasi_readings=self.READINGS,
            declination=1.0, inclination=-30.0, total_intensity=45000.0)
        self.assertEqual(post.call_count, 1)

        payload = post.call_args.kwargs['data']
        self.assertEqual(payload['chat_id'], '-100123')
        text = payload['text']
        self.assertIn('BARTINGTON', text)
        self.assertIn('01-03-2024', text)
        self.assertIn('Jambari', text)
        self.assertIn('Pagi', text)
        self.assertIn('45000', text)          # F (nT)

    def test_mingeo_record_is_not_sent(self):
        """Form MinGeo menulis model yang sama tapi satuannya grad."""
        obs, post = self._create()            # tanpa pembacaan 'deg'
        self.assertFalse(obs.is_bartington)
        self.assertEqual(post.call_count, 0)

    def test_update_does_not_notify(self):
        obs, _ = self._create(deklinasi_readings=self.READINGS)
        with mock.patch('theme.telegram.requests.post') as post:
            with self.captureOnCommitCallbacks(execute=True):
                obs.session = 'Sore'
                obs.save()
        self.assertEqual(post.call_count, 0)

    def test_observer_name_is_escaped(self):
        _, post = self._create(observer='A <b>X</b>', deklinasi_readings=self.READINGS)
        self.assertIn('A &lt;b&gt;X&lt;/b&gt;', post.call_args.kwargs['data']['text'])

    @override_settings(TELEGRAM_BOT_TOKEN='', TELEGRAM_CHAT_ID='')
    def test_no_message_when_telegram_not_configured(self):
        _, post = self._create(deklinasi_readings=self.READINGS)
        self.assertEqual(post.call_count, 0)

    def test_formatting_error_never_breaks_the_save(self):
        with mock.patch('magnet.signals.format_bartington_message',
                        side_effect=ValueError('boom')):
            with mock.patch('theme.telegram.requests.post') as post:
                with self.captureOnCommitCallbacks(execute=True):
                    obs = make_observation(deklinasi_readings=self.READINGS)
        self.assertTrue(MagneticObservation.objects.filter(pk=obs.pk).exists())
        self.assertEqual(post.call_count, 0)


# ── Indeks K: urai citra FMI & batas sumber Excel/FMI ────────────────────────

import io
import os

from openpyxl import Workbook

from .fmi_kindex import FmiLayoutError, parse_k_image, update_kindex_from_image
from .kindex_import import import_kindex_workbook
from .models import KIndexDaily

_TESTDATA = os.path.join(os.path.dirname(__file__), 'testdata')
UTC = datetime.timezone.utc


def _testimage(name):
    with open(os.path.join(_TESTDATA, name), 'rb') as f:
        return f.read()


def _by_day(slots):
    days = {}
    for t, k in slots:
        days.setdefault(t.date(), [None] * 8)[t.hour // 3] = k
    return days


class FmiKIndexParseTest(TestCase):
    """Nilai acuan dibaca manual dari citra BMKG asli di magnet/testdata."""

    def test_parse_storm_image(self):
        slots = parse_k_image(io.BytesIO(_testimage('FMI-K-Indices-JYP-20261017.png')), datetime.date(2026, 10, 17))
        self.assertEqual(len(slots), 48)
        self.assertEqual(slots[0][0], datetime.datetime(2026, 10, 11, 3))
        days = _by_day(slots)
        self.assertEqual(days[datetime.date(2026, 10, 11)], [None, 9, 9, 9, 9, 7, 7, 7])  # K 9 tertutup logo
        self.assertEqual(days[datetime.date(2026, 10, 12)], [4, 4, 4, 1, 2, 2, 3, 3])
        self.assertEqual(days[datetime.date(2026, 10, 13)], [None, 4, 3, 3, 3, 2, 3, 3])  # slot kosong
        self.assertEqual(days[datetime.date(2026, 10, 17)][0], 3)

    def test_parse_quiet_image_with_missing_day(self):
        days = _by_day(parse_k_image(io.BytesIO(_testimage('FMI-K-Indices-JYP-20261003.png')), datetime.date(2026, 10, 3)))
        self.assertEqual(days[datetime.date(2026, 9, 27)], [None, 3, 3, 1, 2, 1, 3, 3])
        self.assertEqual(days[datetime.date(2026, 9, 28)], [None] * 8)
        self.assertEqual(days[datetime.date(2026, 9, 30)], [4, 4, 3, 1, 2, 1, 3, 3])

    def test_unexpected_layout_raises(self):
        buf = io.BytesIO()
        from PIL import Image
        Image.new('RGB', (800, 400), 'white').save(buf, 'PNG')
        buf.seek(0)
        with self.assertRaises(FmiLayoutError):
            parse_k_image(buf, datetime.date(2026, 10, 17))


@override_settings(KINDEX_FMI_START='2026-10-03')
class FmiKIndexUpdateTest(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix='fmi-test-media-')
        self.addCleanup(shutil.rmtree, self.media_root, True)
        ctx = override_settings(MEDIA_ROOT=self.media_root)
        ctx.enable()
        self.addCleanup(ctx.disable)

    def _image(self, name, downloaded):
        obj = FmiIndicesImage.objects.create(jenis='K', tanggal=downloaded.date(),
                                             image=SimpleUploadedFile(name, _testimage(name)))
        FmiIndicesImage.objects.filter(pk=obj.pk).update(updated_at=downloaded)
        obj.refresh_from_db()
        return obj

    def test_only_days_from_cutoff_and_excel_days_untouched(self):
        KIndexDaily.objects.create(tanggal=datetime.date(2026, 9, 30), k_values=[5, 5, 3, 1, 1, 0, 0, 4])
        img = self._image('FMI-K-Indices-JYP-20261003.png', datetime.datetime(2026, 10, 3, 7, 0, tzinfo=UTC))
        days = update_kindex_from_image(img)
        self.assertEqual(days, [datetime.date(2026, 10, 3)])
        sep30 = KIndexDaily.objects.get(tanggal=datetime.date(2026, 9, 30))
        self.assertEqual(sep30.k_values, [5, 5, 3, 1, 1, 0, 0, 4])
        self.assertEqual(sep30.sumber, KIndexDaily.SUMBER_EXCEL)
        oct3 = KIndexDaily.objects.get(tanggal=datetime.date(2026, 10, 3))
        self.assertEqual(oct3.sumber, KIndexDaily.SUMBER_FMI)
        self.assertEqual(oct3.k_values[0], 4)  # batang terakhir citra (kuning)
        self.assertEqual(oct3.k_values[1:], [None] * 7)
        self.assertFalse(oct3.is_complete)
        self.assertEqual(oct3.a_index, 27)  # rata-rata dari slot yang ada (K4 → 27)

    def test_newer_image_overrides_but_blank_slots_do_not_erase(self):
        KIndexDaily.objects.create(tanggal=datetime.date(2026, 10, 13), sumber='fmi',
                                   k_values=[5, 1, 1, 1, 1, 1, 1, 1])
        img = self._image('FMI-K-Indices-JYP-20261017.png', datetime.datetime(2026, 10, 17, 7, 0, tzinfo=UTC))
        update_kindex_from_image(img)
        oct13 = KIndexDaily.objects.get(tanggal=datetime.date(2026, 10, 13))
        self.assertEqual(oct13.k_values, [5, 4, 3, 3, 3, 2, 3, 3])  # slot 0 kosong di citra → nilai lama tetap
        oct11 = KIndexDaily.objects.get(tanggal=datetime.date(2026, 10, 11))
        self.assertEqual(oct11.k_max, 9)
        self.assertEqual(oct11.criteria, 'Badai Besar')

    def test_fetch_command_parses_k_image(self):
        resp = mock.Mock(status_code=200, content=_testimage('FMI-K-Indices-JYP-20261017.png'),
                         headers={'ETag': '"e"'})
        out = io.StringIO()
        with mock.patch(f'{_CMD}.requests.get', return_value=resp), \
                mock.patch('django.utils.timezone.now',
                           return_value=datetime.datetime(2026, 10, 17, 7, 0, tzinfo=UTC)):
            call_command('fetch_fmi_indices', '--jenis', 'K', '--no-telegram', stdout=out)
        self.assertIn('nilai indeks K diurai', out.getvalue())
        self.assertEqual(KIndexDaily.objects.get(tanggal=datetime.date(2026, 10, 12)).k_values, [4, 4, 4, 1, 2, 2, 3, 3])

    def test_fetch_command_survives_unparseable_image(self):
        resp = mock.Mock(status_code=200, content=TINY_PNG, headers={'ETag': '"e"'})
        err = io.StringIO()
        with mock.patch(f'{_CMD}.requests.get', return_value=resp):
            call_command('fetch_fmi_indices', '--jenis', 'K', '--no-telegram', stderr=err)
        self.assertIn('gagal mengurai', err.getvalue())
        self.assertEqual(FmiIndicesImage.objects.count(), 1)  # citra tetap tersimpan

    def test_backfill_command_in_download_order(self):
        self._image('FMI-K-Indices-JYP-20261003.png', datetime.datetime(2026, 10, 3, 7, 0, tzinfo=UTC))
        self._image('FMI-K-Indices-JYP-20261017.png', datetime.datetime(2026, 10, 17, 7, 0, tzinfo=UTC))
        out = io.StringIO()
        call_command('parse_fmi_kindex', stdout=out)
        self.assertIn('Selesai', out.getvalue())
        self.assertTrue(KIndexDaily.objects.filter(tanggal=datetime.date(2026, 10, 3)).exists())
        self.assertFalse(KIndexDaily.objects.filter(tanggal__lt=datetime.date(2026, 10, 3)).exists())

    def test_excel_import_skips_days_from_cutoff(self):
        wb = Workbook()
        ws = wb.active
        ws.title = 'Oktober'
        ws['K2'] = 2026
        for day in range(1, 32):
            ws.cell(4 + day, 1, day)
            for j in range(8):
                ws.cell(4 + day, 2 + j, 2)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        summary, warnings = import_kindex_workbook(buf, 2026, 'k.xlsx')
        self.assertEqual(summary['2026-10']['data'], 2)  # hanya 1–2 Oktober
        self.assertTrue(any('dilewati' in w for w in warnings))
        self.assertEqual(KIndexDaily.objects.get(tanggal=datetime.date(2026, 10, 2)).sumber, 'excel')
        self.assertFalse(KIndexDaily.objects.filter(tanggal=datetime.date(2026, 10, 3)).exists())
