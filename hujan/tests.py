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


# ── Notifikasi Telegram ──────────────────────────────────────────────────────
from unittest import mock

from django.test import override_settings


@override_settings(TELEGRAM_BOT_TOKEN='tok-123', TELEGRAM_CHAT_ID='-100123')
class HujanTelegramNotifyTest(TestCase):
    """Setiap data hujan baru dikabarkan ke Telegram (input manual)."""

    def _create(self, **kwargs):
        """Buat record sambil menangkap callback on_commit dan HTTP call-nya."""
        with mock.patch('theme.telegram.requests.post') as post:
            post.return_value = mock.Mock(status_code=200, text='')
            with self.captureOnCommitCallbacks(execute=True):
                record = make_hujan(**kwargs)
        return record, post

    def test_new_record_is_sent_to_telegram(self):
        record, post = self._create(obs=12.5, kategori='Sedang', petugas='Staff Ops')
        self.assertEqual(post.call_count, 1)

        payload = post.call_args.kwargs['data']
        self.assertEqual(payload['chat_id'], '-100123')
        self.assertEqual(payload['parse_mode'], 'HTML')

        text = payload['text']
        self.assertIn('DATA HUJAN BARU', text)
        self.assertIn('01-03-2024', text)
        self.assertIn('12.5', text)
        self.assertIn('Sedang', text)
        self.assertIn('Staff Ops', text)

    def test_token_is_used_in_the_url(self):
        _, post = self._create()
        self.assertIn('bottok-123/sendMessage', post.call_args.args[0])

    def test_operator_entered_text_is_html_escaped(self):
        """Keterangan/petugas bisa berisi < & > — jangan sampai merusak pesan."""
        _, post = self._create(petugas='Ops <A&B>', keterangan='<b>deras</b>')
        text = post.call_args.kwargs['data']['text']
        self.assertIn('Ops &lt;A&amp;B&gt;', text)
        self.assertIn('&lt;b&gt;deras&lt;/b&gt;', text)

    def test_blank_keterangan_shows_dash(self):
        _, post = self._create(keterangan=None)
        self.assertIn('Keterangan: -', post.call_args.kwargs['data']['text'])

    def test_update_does_not_notify(self):
        record, _ = self._create()
        with mock.patch('theme.telegram.requests.post') as post:
            with self.captureOnCommitCallbacks(execute=True):
                record.kategori = 'Lebat'
                record.save()
        self.assertEqual(post.call_count, 0)

    def test_bulk_create_does_not_notify(self):
        """Impor otomatis memakai bulk_create -> tidak ada pesan (sesuai keputusan)."""
        with mock.patch('theme.telegram.requests.post') as post:
            with self.captureOnCommitCallbacks(execute=True):
                Hujan.objects.bulk_create([
                    Hujan(tanggal=datetime.date(2024, 3, 5), hilman=1.0, obs=1.0,
                          kategori='Ringan', petugas='Importer'),
                ])
        self.assertEqual(post.call_count, 0)

    @override_settings(TELEGRAM_BOT_TOKEN='', TELEGRAM_CHAT_ID='')
    def test_no_message_when_telegram_not_configured(self):
        _, post = self._create()
        self.assertEqual(post.call_count, 0)

    def test_telegram_failure_does_not_break_saving(self):
        """Notifikasi gagal bukan alasan data hujan batal tersimpan."""
        import requests
        with mock.patch('theme.telegram.requests.post') as post:
            post.side_effect = requests.RequestException('jaringan mati')
            with self.captureOnCommitCallbacks(execute=True):
                record = make_hujan(obs=99.9)
        self.assertTrue(Hujan.objects.filter(pk=record.pk).exists())

    def test_daily_import_is_no_longer_scheduled(self):
        """Impor hujan harian dimatikan (data kini diinput manual)."""
        from django.conf import settings
        scheduled = [k for k in settings.CELERY_BEAT_SCHEDULE if 'hujan' in k.lower()]
        self.assertEqual(scheduled, [])

    def test_import_task_still_exists_for_manual_use(self):
        from hujan.tasks import import_today_hujan_data
        self.assertTrue(callable(import_today_hujan_data))
