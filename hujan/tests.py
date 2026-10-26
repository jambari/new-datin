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

    def test_string_date_does_not_crash_the_signal(self):
        """Record bisa saja dibuat dengan tanggal string (fixture/command)."""
        _, post = self._create(tanggal='2026-10-02')
        self.assertEqual(post.call_count, 1)
        self.assertIn('2026-10-02', post.call_args.kwargs['data']['text'])

    def test_formatting_error_never_breaks_the_save(self):
        """Notifikasi adalah efek samping: gagal menyusun pesan != data hilang."""
        with mock.patch('hujan.signals.format_hujan_message',
                        side_effect=ValueError('boom')):
            with mock.patch('theme.telegram.requests.post') as post:
                with self.captureOnCommitCallbacks(execute=True):
                    record = make_hujan(obs=55.5)
        self.assertTrue(Hujan.objects.filter(pk=record.pk).exists())
        self.assertEqual(post.call_count, 0)


class HujanKategoriNormalizeTest(TestCase):
    def test_normalize_variants(self):
        from .categories import normalize_kategori, kategori_label
        cases = {
            'Nihil': 'nihil', 'NIHIIL': 'nihil', ' Sangat Ringan': 'sangat ringan',
            'Hujan Sangat  Ringan': 'sangat ringan', 'Hujan Sanga t Ringan': 'sangat ringan',
            'Hukan Ringan': 'ringan', 'Huan Sedang': 'sedang', 'hujan sangat lebat': 'sangat lebat',
            'TTU': 'tak terukur', 'tak terukur': 'tak terukur', '': '', None: '',
        }
        for raw, key in cases.items():
            self.assertEqual(normalize_kategori(raw), key, raw)
        self.assertIsNone(normalize_kategori('gerimis'))
        self.assertEqual(kategori_label('Hujan Lebat'), 'Lebat')
        self.assertEqual(kategori_label('gerimis'), 'Lainnya')

    def test_command_normalizes_and_backs_up(self):
        import json, os, tempfile, io
        from django.core.management import call_command
        a = Hujan.objects.create(tanggal=datetime.date(2010, 1, 1), obs=0, kategori='Nihil')
        b = Hujan.objects.create(tanggal=datetime.date(2010, 1, 2), obs=3, kategori='Hujan Sangat Ringan')
        c = Hujan.objects.create(tanggal=datetime.date(2026, 1, 1), obs=12, kategori='ringan')
        d = Hujan.objects.create(tanggal=datetime.date(2010, 1, 3), obs=0, kategori='')
        out = io.StringIO()
        call_command('normalize_hujan_kategori', '--dry-run', stdout=out)
        self.assertIn('2 record akan diubah', out.getvalue())
        self.assertEqual(Hujan.objects.get(pk=a.pk).kategori, 'Nihil')
        with tempfile.TemporaryDirectory() as tmp:
            backup = os.path.join(tmp, 'b.json')
            call_command('normalize_hujan_kategori', '--backup', backup, stdout=io.StringIO())
            saved = {r['pk']: r['kategori'] for r in json.load(open(backup))}
        self.assertEqual(saved, {a.pk: 'Nihil', b.pk: 'Hujan Sangat Ringan'})
        self.assertEqual([Hujan.objects.get(pk=x.pk).kategori for x in (a, b, c, d)],
                         ['nihil', 'sangat ringan', 'ringan', ''])


# ── Lampiran Sampel Hujan ────────────────────────────────────────────────────
class LampiranSampelHujanTest(TestCase):
    def setUp(self):
        from jadwal.models import JadwalHarian, Pegawai, PolaDinas
        self.user = User.objects.create_user('sampler', password='pass123')
        self.client.login(username='sampler', password='pass123')
        ps = PolaDinas.objects.create(kode='PS', nama='Pagi Siang', jam_mulai='07:00', jam_selesai='19:00', durasi=12)
        libur = PolaDinas.objects.create(kode='L', nama='Libur', jam_mulai='00:00', jam_selesai='00:00', durasi=0, is_libur=True)
        monday = datetime.date(2026, 10, 5)
        for i, (nama, pola) in enumerate([('ALIF MUHAMMAD ANNABAL, S.Tr.Inst, M.Sc', ps),
                                          ('ANAS TAUFIQ SYARIFUDDIN, S.Tr.Inst', ps),
                                          ('JAMBARI, S.Tr, M.Si', libur)]):
            p = Pegawai.objects.create(nama=nama, nip=str(i), pangkat='-', jabatan='-', urutan=i)
            JadwalHarian.objects.create(pegawai=p, tanggal=monday, pola=pola)
        for day, obs, kat in [(29, 0, 'nihil'), (30, 0.8, 'sangat ringan'), (1, 73.7, 'sangat lebat'), (5, 0, 'nihil')]:
            month = 9 if day > 20 else 10
            make_hujan(tanggal=datetime.date(2026, month, day), obs=obs, kategori=kat, petugas='JAMBARI, S.Tr, M.Si')
        self.params = {'start': '2026-09-29', 'end': '2026-10-05'}

    def test_sampling_info_uses_week_of_start_month_and_ps_roster(self):
        from .lampiran import sampling_info
        info = sampling_info(datetime.date(2026, 9, 29), datetime.date(2026, 10, 5))
        self.assertEqual(info['minggu'], 'V (Lima) / V (Lima)')
        self.assertEqual(info['bulan_tahun'], 'September / 2026')
        self.assertAlmostEqual(info['total'], 74.5)
        self.assertEqual(info['kondisi'], 'Baik')
        self.assertEqual(info['pengamat'], ['Alif Muhammad Annabal', 'Anas Taufiq Syarifuddin'])

    def test_query_page_shows_sampling_block_and_export_link(self):
        resp = self.client.get(reverse('query_laporan_hujan'), self.params)
        self.assertContains(resp, 'Periode Sampling / Minggu ke')
        self.assertContains(resp, 'Anas Taufiq Syarifuddin')
        self.assertContains(resp, reverse('lampiran_sampel_hujan_pdf'))

    def test_pdf_export(self):
        resp = self.client.get(reverse('lampiran_sampel_hujan_pdf'), {**self.params, 'kondisi': 'Baik'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertIn('Lampiran_Sampel_Hujan_20261005.pdf', resp['Content-Disposition'])
        self.assertTrue(resp.content.startswith(b'%PDF'))

    def test_pdf_export_rejects_bad_dates(self):
        resp = self.client.get(reverse('lampiran_sampel_hujan_pdf'), {'start': '2026-10-05', 'end': '2026-09-29'})
        self.assertEqual(resp.status_code, 400)
        resp = self.client.get(reverse('lampiran_sampel_hujan_pdf'), {'start': 'x', 'end': ''})
        self.assertEqual(resp.status_code, 400)

    def test_pdf_export_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse('lampiran_sampel_hujan_pdf'), self.params)
        self.assertEqual(resp.status_code, 302)
