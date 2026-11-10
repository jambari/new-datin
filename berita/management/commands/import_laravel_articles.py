"""Impor artikel dari website Laravel lama (.188, tabel MySQL `articles`) ke aplikasi Berita.

Masukan: JSON hasil ekstraksi dump MySQL (satu objek per artikel: id, category, title, slug, author,
content, image, status, date, created_at, deleted_at, media[]). Tiap media berisi `kind` (cover/content),
`url` (seperti tertulis di artikel lama) dan `found` (path berkas di .188, atau null bila hilang).
Berkas foto yang ditemukan disalin ke --media-root dengan path yang sama (tanpa '/' di depan).

- Hanya kategori berita stasiun (--categories) yang diimpor; artikel terhapus/draf dilewati.
- Slug lama dipakai apa adanya, sehingga tautan lama /berita/<slug> tetap sama polanya.
- Artikel yang slug-nya sudah ada dilewati (aman dijalankan ulang).
- Foto yang ditemukan diunggah ulang (sampul → cover, foto di isi → berita/content/...);
  <img> yang berkasnya hilang dibuang dari isi.
- Isi dibersihkan dengan sanitizer yang sama dengan editor Berita.

    python manage.py import_laravel_articles articles.json --media-root /tmp/laravel_media --dry-run
    python manage.py import_laravel_articles articles.json --media-root /tmp/laravel_media
"""
import datetime
import html
import json
import re
import uuid
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from berita.models import Berita
from berita.sanitize import clean_html

DEFAULT_CATEGORIES = 'berita,kunjungan,sosialisasi,maintenis,survei,olahraga'
WIT = datetime.timezone(datetime.timedelta(hours=9))
IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
_IMG = re.compile(r'<img\b[^>]*?\bsrc\s*=\s*(["\'])(.*?)\1[^>]*>', re.I | re.S)


def _excerpt(content, words=35):
    text = re.sub(r'<(?:br|/p|/div|/li|/h[1-6]|/td|/tr)\b[^>]*>', ' ', clean_html(content or ''), flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', html.unescape(text)).strip()
    parts = text.split(' ')
    return ' '.join(parts[:words]) + ('…' if len(parts) > words else '')


def _published_at(article):
    for key in ('created_at',):
        value = article.get(key)
        if value and not value.startswith('0000'):
            try:
                t = datetime.datetime.strptime(value[:19], '%Y-%m-%d %H:%M:%S')
                if article.get('date') and t.date().isoformat() == article['date']:
                    return t.replace(tzinfo=WIT)
            except ValueError:
                pass
    return datetime.datetime.strptime(article['date'], '%Y-%m-%d').replace(hour=9, tzinfo=WIT)


def _image_bytes(media, root):
    """Isi berkas foto yang ditemukan, atau None (hilang / bukan gambar / tidak terbaca)."""
    found = media.get('found')
    if not found or found.startswith('zip:') or media.get('candidates'):
        return None, None                              # hanya cocok path; cocok nama saja tidak dipercaya
    path = Path(root) / found.lstrip('/')
    ext = path.suffix.lower()
    if ext not in IMAGE_EXT or not path.is_file():
        return None, None
    data = path.read_bytes()
    try:
        from PIL import Image
        import io
        Image.open(io.BytesIO(data)).verify()
    except Exception:
        return None, None
    return data, ('.jpg' if ext == '.jpeg' else ext)


class Command(BaseCommand):
    help = 'Impor artikel website Laravel lama (.188) ke aplikasi Berita.'

    def add_arguments(self, parser):
        parser.add_argument('json_path')
        parser.add_argument('--media-root', required=True, help='Folder berisi foto yang ditemukan (path .188).')
        parser.add_argument('--categories', default=DEFAULT_CATEGORIES,
                            help=f'Kategori yang diimpor, dipisah koma (bawaan: {DEFAULT_CATEGORIES}).')
        parser.add_argument('--dry-run', action='store_true', help='Tampilkan rencana tanpa menyimpan.')

    def handle(self, *args, json_path, media_root, categories, dry_run, **opts):
        try:
            articles = json.loads(Path(json_path).read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise CommandError(f'JSON tidak terbaca: {exc}')
        wanted = {c.strip().lower() for c in categories.split(',') if c.strip()}
        stats = {'diimpor': 0, 'sudah ada': 0, 'dilewati': 0, 'sampul': 0, 'foto isi': 0, 'foto hilang': 0}

        for a in sorted(articles, key=lambda x: (x.get('date') or '', int(x['id']))):
            if (a.get('category') or '').lower() not in wanted:
                continue
            if a.get('deleted_at') or (a.get('status') or 'PUBLISHED') != 'PUBLISHED':
                stats['dilewati'] += 1
                continue
            slug = (a.get('slug') or '').strip()[:240]
            if slug and Berita.objects.filter(slug=slug).exists():
                stats['sudah ada'] += 1
                continue

            media = a.get('media') or []
            cover_media = next((m for m in media if m['kind'] == 'cover'), None)
            cover = _image_bytes(cover_media, media_root) if cover_media else (None, None)
            content = a.get('content') or ''
            inline = {}                                 # url lama → (data, ext) atau None
            for m in media:
                if m['kind'] == 'content':
                    inline[m['url']] = _image_bytes(m, media_root)
            missing = sum(1 for m in media if not (_image_bytes(m, media_root)[0]))
            stats['foto hilang'] += missing

            self.stdout.write(f"{'[rencana] ' if dry_run else ''}#{a['id']} {a['date']} {a['category']}: "
                              f"{a['title'][:70]} | sampul {'ada' if cover[0] else '-'}, "
                              f"foto isi {sum(1 for v in inline.values() if v and v[0])}/{len(inline)}")
            if dry_run:
                stats['diimpor'] += 1
                stats['sampul'] += bool(cover[0])
                stats['foto isi'] += sum(1 for v in inline.values() if v and v[0])
                continue

            with transaction.atomic():
                def replace(match):
                    url = match.group(2)
                    got = inline.get(url)
                    if not got or not got[0]:
                        return ''                       # foto hilang: buang tag
                    data, ext = got
                    name = f'berita/content/{_published_at(a):%Y/%m}/{uuid.uuid4().hex[:16]}{ext}'
                    saved = default_storage.save(name, ContentFile(data))
                    stats['foto isi'] += 1
                    return match.group(0).replace(url, default_storage.url(saved))

                body = _IMG.sub(replace, content)
                if (a.get('author') or '').strip():
                    body += f'<p><em>Penulis: {html.escape(a["author"].strip())}</em></p>'
                obj = Berita(
                    title=a['title'][:220],
                    slug=slug,
                    excerpt=_excerpt(content),
                    content=clean_html(body),
                    status=Berita.STATUS_PUBLISHED,
                    published_at=_published_at(a),
                )
                if cover[0]:
                    obj.cover.save(f'laravel-{a["id"]}{cover[1]}', ContentFile(cover[0]), save=False)
                    stats['sampul'] += 1
                obj.save()
            stats['diimpor'] += 1

        verb = 'akan diimpor' if dry_run else 'diimpor'
        self.stdout.write(self.style.SUCCESS(
            f"{stats['diimpor']} artikel {verb}; {stats['sudah ada']} sudah ada; {stats['dilewati']} terhapus/draf; "
            f"sampul {stats['sampul']}, foto isi {stats['foto isi']}, referensi foto hilang {stats['foto hilang']}."))
