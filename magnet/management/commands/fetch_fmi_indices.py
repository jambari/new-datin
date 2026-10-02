"""
Scrape citra indeks magnetbumi harian (K & A) Stasiun Geofisika Jayapura,
simpan ke database, lalu kirim ke grup Telegram.

Sumber citra:
    https://dataweb.bmkg.go.id/geofisika/magnet/FMI-K-Indices-JYP.png?ssl=1
    https://dataweb.bmkg.go.id/geofisika/magnet/FMI-A-Indices-JYP.png?ssl=1

Dijalankan otomatis oleh Celery beat setiap 16:00 WIT (07:00 UTC), lihat
CELERY_BEAT_SCHEDULE['fetch-fmi-indices-daily'].

Manual:
    python manage.py fetch_fmi_indices
    python manage.py fetch_fmi_indices --date 2026-10-01     # isi data historis
    python manage.py fetch_fmi_indices --jenis K             # hanya satu jenis
    python manage.py fetch_fmi_indices --no-telegram         # tanpa kirim Telegram
    python manage.py fetch_fmi_indices --force               # kirim ulang walau citra sama
"""

import hashlib
import subprocess
import time
from datetime import datetime

import requests
import zoneinfo
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from magnet.models import FmiIndicesImage

_WIT = zoneinfo.ZoneInfo('Asia/Jayapura')

_BASE_URL = 'https://dataweb.bmkg.go.id/geofisika/magnet/FMI-{jenis}-Indices-JYP.png?ssl=1'

_HEADERS = {
    # Beberapa endpoint BMKG menolak request tanpa User-Agent yang wajar.
    'User-Agent': 'Mozilla/5.0 (compatible; DatinGeofisikaJayapura/1.0)',
    'Accept': 'image/png,image/*;q=0.8,*/*;q=0.5',
    'Referer': 'https://dataweb.bmkg.go.id/geofisika/magnet/',
}

_PNG_MAGIC = b'\x89PNG\r\n\x1a\n'

_JENIS_LABEL = {
    FmiIndicesImage.K: 'K Indices',
    FmiIndicesImage.A: 'A Indices',
}


def _fetch_png(url, attempts=3):
    """Ambil citra PNG dengan retry sederhana. Mengembalikan (bytes, etag)."""
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=(10, 30))
            if resp.status_code == 200:
                content = resp.content
                if not content.startswith(_PNG_MAGIC):
                    last_error = (
                        f'respons bukan PNG (Content-Type={resp.headers.get("Content-Type")!r}, '
                        f'{len(content)} byte)'
                    )
                else:
                    return content, (resp.headers.get('ETag') or '')[:100]
            else:
                last_error = f'HTTP {resp.status_code}'
        except requests.RequestException as exc:
            last_error = f'{type(exc).__name__}: {exc}'

        if attempt < attempts:
            time.sleep(2 * attempt)

    raise CommandError(f'Gagal mengambil {url} setelah {attempts} percobaan: {last_error}')


def _url_for(jenis):
    return _BASE_URL.format(jenis=jenis)


def _store_image(obj, content):
    """Tulis file citra ke storage dengan nama deterministik (overwrite)."""
    storage = obj.image.storage
    rel_path = f'magnet/fmi_indices/{obj.tanggal:%Y/%m}/{obj.filename}'

    # Hapus file lama bila path-nya berbeda (mis. baris ini dulunya tanggal lain).
    old_name = obj.image.name
    if old_name and old_name != rel_path and storage.exists(old_name):
        storage.delete(old_name)

    # Overwrite: FileSystemStorage menambah suffix acak bila file sudah ada.
    if storage.exists(rel_path):
        storage.delete(rel_path)
    storage.save(rel_path, ContentFile(content))

    obj.image.name = rel_path
    return rel_path


def _send_photo(image_path, caption):
    """Kirim satu citra ke grup Telegram. Mengembalikan (sukses: bool, pesan: str)."""
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return False, 'TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID belum diset'

    cmd = [
        'curl', '-s', '-X', 'POST',
        f'https://api.telegram.org/bot{token}/sendPhoto',
        '-F', f'chat_id={chat_id}',
        '-F', f'photo=@{image_path}',
        '-F', 'parse_mode=HTML',
        # --form-string: jangan biarkan curl menafsirkan '@' / '<' di caption.
        '--form-string', f'caption={caption}',
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.SubprocessError as exc:
        return False, f'{type(exc).__name__}: {exc}'

    body = (result.stdout or '').strip()
    if '"ok":true' in body.replace(' ', ''):
        return True, body
    return False, body or (result.stderr or '').strip() or 'tidak ada respons'


class Command(BaseCommand):
    help = 'Ambil citra indeks magnetbumi K & A (JYP), simpan ke DB, kirim ke Telegram'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            help='Tanggal (WIT) yang disimpan, format YYYY-MM-DD. Default: hari ini WIT.',
        )
        parser.add_argument(
            '--jenis',
            choices=['K', 'A', 'all'],
            default='all',
            help='Jenis indeks yang diambil. Default: all.',
        )
        parser.add_argument(
            '--no-telegram',
            action='store_true',
            help='Simpan ke database saja, jangan kirim ke Telegram.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Kirim ulang ke Telegram walaupun citra tidak berubah.',
        )

    def handle(self, *args, **options):
        now_wit = timezone.now().astimezone(_WIT)

        tanggal = now_wit.date()
        if options['date']:
            try:
                tanggal = datetime.strptime(options['date'], '%Y-%m-%d').date()
            except ValueError:
                raise CommandError('Format --date harus YYYY-MM-DD')

        if options['jenis'] == 'all':
            jenis_list = [FmiIndicesImage.K, FmiIndicesImage.A]
        else:
            jenis_list = [options['jenis']]

        send_telegram = not options['no_telegram']
        force = options['force']

        self.stdout.write(f'[fmi-indices] tanggal={tanggal} WIT | jenis={",".join(jenis_list)}')

        errors = []
        for jenis in jenis_list:
            url = _url_for(jenis)
            try:
                content, etag = _fetch_png(url)
            except CommandError as exc:
                self.stderr.write(self.style.ERROR(f'  {jenis}: {exc}'))
                errors.append(f'{jenis}: {exc}')
                continue

            sha = hashlib.sha256(content).hexdigest()
            obj, created = FmiIndicesImage.objects.get_or_create(
                jenis=jenis,
                tanggal=tanggal,
                defaults={'source_url': url},
            )
            unchanged = (not created) and obj.sha256 == sha

            obj.source_url = url
            obj.etag = etag
            obj.sha256 = sha
            obj.size_bytes = len(content)
            _store_image(obj, content)
            obj.save()

            action = 'dibuat' if created else ('tidak berubah' if unchanged else 'diperbarui')
            self.stdout.write(
                f'  {jenis}: {action} — {len(content)} byte, sha256={sha[:12]}…, file={obj.image.name}'
            )

            if not send_telegram:
                continue

            if unchanged and not force and obj.telegram_sent_at:
                self.stdout.write(f'  {jenis}: citra sama & sudah terkirim — Telegram dilewati')
                continue

            caption = (
                f'🧭 <b>Indeks Magnetbumi {_JENIS_LABEL[jenis]}</b> — JYP\n'
                f'📅 {tanggal:%d %B %Y} (WIT)\n'
                f'🕓 Diambil {now_wit:%H:%M} WIT'
            )
            ok, message = _send_photo(obj.image.path, caption)
            if ok:
                obj.telegram_sent_at = timezone.now()
                obj.save(update_fields=['telegram_sent_at'])
                self.stdout.write(self.style.SUCCESS(f'  {jenis}: terkirim ke Telegram'))
            else:
                # Jangan gagalkan seluruh job hanya karena Telegram.
                self.stderr.write(self.style.WARNING(f'  {jenis}: Telegram gagal — {message[:200]}'))

        if errors:
            raise CommandError('Sebagian pengambilan citra gagal: ' + '; '.join(errors))

        self.stdout.write(self.style.SUCCESS('[fmi-indices] selesai'))
