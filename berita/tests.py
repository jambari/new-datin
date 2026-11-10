import io
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import Berita
from .sanitize import clean_html


def make_berita(**kwargs):
    defaults = {
        'title': 'Gempa M5,2 Guncang Jayapura',
        'content': '<p>Informasi gempa terbaru dari BMKG Jayapura.</p>',
        'excerpt': 'Ringkasan berita gempa.',
        'status': Berita.STATUS_PUBLISHED,
    }
    defaults.update(kwargs)
    return Berita.objects.create(**defaults)


class SanitizeTests(TestCase):
    def test_script_and_event_handlers_removed(self):
        html = ('<p onclick="alert(1)">Aman</p>'
                '<script>alert(2)</script>'
                '<img src="x" onerror="alert(3)">')
        cleaned = clean_html(html)
        self.assertIn('<p>Aman</p>', cleaned)
        self.assertNotIn('script', cleaned.lower())
        self.assertNotIn('onclick', cleaned.lower())
        self.assertNotIn('onerror', cleaned.lower())

    def test_javascript_url_removed(self):
        cleaned = clean_html('<a href="javascript:alert(1)">klik</a>')
        self.assertNotIn('javascript:', cleaned.lower())
        self.assertIn('<a>klik</a>', cleaned)

    def test_safe_formatting_kept(self):
        html = '<h2>Judul</h2><p><strong>Tebal</strong> dan <em>miring</em></p><ul><li>Satu</li></ul>'
        cleaned = clean_html(html)
        self.assertEqual(cleaned, html)


class BeritaModelTests(TestCase):
    def test_slug_generated_and_unique(self):
        first = make_berita(title='Berita Gempa')
        second = make_berita(title='Berita Gempa')
        self.assertEqual(first.slug, 'berita-gempa')
        self.assertEqual(second.slug, 'berita-gempa-2')

    def test_publishing_sets_published_at(self):
        berita = make_berita()
        self.assertIsNotNone(berita.published_at)
        self.assertTrue(berita.is_published)

    def test_draft_not_published(self):
        berita = make_berita(status=Berita.STATUS_DRAFT)
        self.assertFalse(berita.is_published)


class BeritaPublicTests(TestCase):
    def setUp(self):
        self.published = make_berita(title='Berita Terbit')
        self.draft = make_berita(title='Berita Draf', status=Berita.STATUS_DRAFT)

    def test_list_only_shows_published(self):
        response = self.client.get(reverse('berita:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Berita Terbit')
        self.assertNotContains(response, 'Berita Draf')

    def test_detail_published(self):
        response = self.client.get(self.published.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bagikan artikel ini')
        self.assertContains(response, 'fb-comments')
        self.assertContains(response, 'WhatsApp')

    def test_draft_detail_hidden_from_public(self):
        response = self.client.get(self.draft.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_author_can_preview_own_draft(self):
        author = User.objects.create_user('penulis', password='pass12345')
        draft = make_berita(title='Draf Penulis', author=author,
                            status=Berita.STATUS_DRAFT)
        self.client.force_login(author)
        response = self.client.get(draft.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'PRATINJAU DRAF')

    def test_landing_shows_news_menu_and_panel(self):
        response = self.client.get(reverse('landing'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('berita:list'))
        self.assertContains(response, 'Berita Terbaru')
        self.assertContains(response, 'Berita Terbit')

    def test_sitemap_lists_article(self):
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.published.get_absolute_url())


class BeritaCrudTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user('penulis', password='pass12345')
        self.other = User.objects.create_user('lain', password='pass12345')

    def test_create_requires_login(self):
        response = self.client.get(reverse('berita:create'))
        self.assertEqual(response.status_code, 302)

    def test_create_article(self):
        self.client.force_login(self.author)
        response = self.client.post(reverse('berita:create'), {
            'title': 'Berita Baru',
            'slug': '',
            'excerpt': 'Ringkasan.',
            'content': '<p>Isi berita baru.</p>',
            'status': Berita.STATUS_PUBLISHED,
        })
        self.assertEqual(response.status_code, 302)
        berita = Berita.objects.get(title='Berita Baru')
        self.assertEqual(berita.author, self.author)
        self.assertEqual(berita.slug, 'berita-baru')

    def test_content_is_sanitized(self):
        self.client.force_login(self.author)
        self.client.post(reverse('berita:create'), {
            'title': 'Berita XSS',
            'content': '<p>Isi</p><script>alert(1)</script>',
            'status': Berita.STATUS_DRAFT,
        })
        berita = Berita.objects.get(title='Berita XSS')
        self.assertNotIn('<script>', berita.content)

    def test_empty_content_rejected(self):
        self.client.force_login(self.author)
        response = self.client.post(reverse('berita:create'), {
            'title': 'Tanpa Isi',
            'content': '<p><br></p>',
            'status': Berita.STATUS_DRAFT,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Berita.objects.filter(title='Tanpa Isi').exists())

    def test_author_can_edit_but_other_cannot(self):
        berita = make_berita(author=self.author)
        url = reverse('berita:update', args=[berita.slug])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.author)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_author_can_delete(self):
        berita = make_berita(author=self.author)
        self.client.force_login(self.author)
        response = self.client.post(reverse('berita:delete', args=[berita.slug]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Berita.objects.filter(pk=berita.pk).exists())

    def test_manage_page_shows_sidebar_crud_links(self):
        self.client.force_login(self.author)
        response = self.client.get(reverse('berita:manage'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('berita:create'))
        self.assertContains(response, 'Tulis Berita')


class BeritaUploadTests(TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.user = User.objects.create_user('penulis', password='pass12345')
        self.url = reverse('berita:upload_image')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _png(self):
        buf = io.BytesIO()
        Image.new('RGB', (8, 8), 'red').save(buf, format='PNG')
        return SimpleUploadedFile('gambar.png', buf.getvalue(), content_type='image/png')

    def test_upload_requires_login(self):
        response = self.client.post(self.url, {'image': self._png()})
        self.assertEqual(response.status_code, 302)

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_upload_returns_url(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {'image': self._png()})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('/media/berita/content/', payload['url'])

    def test_upload_rejects_non_image(self):
        self.client.force_login(self.user)
        bad = SimpleUploadedFile('x.png', b'bukan gambar', content_type='image/png')
        response = self.client.post(self.url, {'image': bad})
        self.assertEqual(response.status_code, 400)


class ImportLaravelArticlesTest(TestCase):
    """Impor artikel website Laravel lama (.188)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='berita-import-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        ctx = override_settings(MEDIA_ROOT=f'{self.tmp}/media')
        ctx.enable()
        self.addCleanup(ctx.disable)
        self.src = f'{self.tmp}/src'
        photo = f'{self.src}/var/www/html/datin/public/berita/berita/ogd'
        import os
        os.makedirs(photo)
        buf = io.BytesIO()
        Image.new('RGB', (8, 8), 'red').save(buf, 'JPEG')
        for name in ('sampul.jpeg', 'isi.jpeg'):
            with open(f'{photo}/{name}', 'wb') as fh:
                fh.write(buf.getvalue())
        base = '/var/www/html/datin/public/berita/berita/ogd/'
        self.articles = [
            {'id': '72', 'category': 'berita', 'title': 'Kegiatan OGD', 'slug': 'kegiatan-ogd', 'author': 'Jambari',
             'content': '<p>Isi <b>berita</b>.</p><img src="../../berita/berita/ogd/isi.jpeg">'
                        '<img src="berita/berita/hilang.jpg"><script>alert(1)</script>',
             'image': 'berita/berita/ogd/sampul.jpeg', 'status': 'PUBLISHED', 'date': '2019-04-18',
             'created_at': '2019-04-18 21:05:00', 'deleted_at': None,
             'media': [{'kind': 'cover', 'url': 'berita/berita/ogd/sampul.jpeg', 'found': base + 'sampul.jpeg'},
                       {'kind': 'content', 'url': '../../berita/berita/ogd/isi.jpeg', 'found': base + 'isi.jpeg'},
                       {'kind': 'content', 'url': 'berita/berita/hilang.jpg', 'found': None}]},
            {'id': '80', 'category': 'seismisitas', 'title': 'Review', 'slug': 'review', 'author': 'x', 'content': 'x',
             'image': None, 'status': 'PUBLISHED', 'date': '2019-09-09', 'created_at': None, 'deleted_at': None,
             'media': []},
            {'id': '81', 'category': 'kunjungan', 'title': 'Terhapus', 'slug': 'terhapus', 'author': 'x',
             'content': 'x', 'image': None, 'status': 'PUBLISHED', 'date': '2019-09-09', 'created_at': None,
             'deleted_at': '2020-01-01 00:00:00', 'media': []},
            {'id': '82', 'category': 'kunjungan', 'title': 'Nama Saja', 'slug': 'nama-saja', 'author': '',
             'content': '<p>Teks</p>', 'image': 'x/1.jpg', 'status': 'PUBLISHED', 'date': '2020-02-02',
             'created_at': None, 'deleted_at': None,
             'media': [{'kind': 'cover', 'url': 'x/1.jpg', 'found': base + 'sampul.jpeg', 'candidates': 6}]},
        ]
        self.json = f'{self.tmp}/a.json'
        import json
        with open(self.json, 'w') as fh:
            json.dump(self.articles, fh)

    def run_import(self, *extra):
        from django.core.management import call_command
        out = io.StringIO()
        call_command('import_laravel_articles', self.json, '--media-root', self.src, *extra, stdout=out)
        return out.getvalue()

    def test_dry_run_saves_nothing(self):
        out = self.run_import('--dry-run')
        self.assertIn('2 artikel akan diimpor', out)
        self.assertEqual(Berita.objects.count(), 0)

    def test_import_keeps_slug_date_photos_and_is_idempotent(self):
        import datetime
        out = self.run_import()
        self.assertIn('2 artikel diimpor', out)
        self.assertIn('1 terhapus/draf', out)
        b = Berita.objects.get(slug='kegiatan-ogd')
        self.assertTrue(b.is_published)
        self.assertEqual(b.published_at, datetime.datetime(2019, 4, 18, 12, 5, tzinfo=datetime.timezone.utc))
        self.assertTrue(b.cover.name.startswith('berita/covers/'))
        self.assertEqual(b.content.count('<img'), 1)                 # foto hilang dibuang
        self.assertIn('/media/berita/content/2019/04/', b.content)
        self.assertNotIn('script', b.content)
        self.assertIn('Penulis: Jambari', b.content)
        self.assertEqual(b.excerpt, 'Isi berita.')
        self.assertFalse(Berita.objects.filter(slug='review').exists())     # kategori lain tidak diimpor
        self.assertFalse(Berita.objects.get(slug='nama-saja').cover)         # cocok nama saja: tidak dipakai
        self.assertIn('0 artikel diimpor; 2 sudah ada', self.run_import())
        self.assertEqual(self.client.get('/berita/kegiatan-ogd/').status_code, 200)
