"""
Scan media/arsip_foto/ and import photos/videos into the database.

Each direct subfolder of arsip_foto/ becomes one Album.
Supports nested subfolders — all media inside an album folder (recursive) is imported.

Usage:
  python manage.py import_foto               # import new files only
  python manage.py import_foto --rethumbnail # regenerate thumbnails
  python manage.py import_foto --dry-run     # report counts, no DB writes
"""
import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone as tz

from arsip.models import Album, Foto, VIDEO_EXTENSIONS

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
SUPPORTED = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
THUMB_SIZE = (220, 220)


class Command(BaseCommand):
    help = 'Import photos/videos from media/arsip_foto/ into the database'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--rethumbnail', action='store_true')

    def handle(self, *args, **options):
        try:
            from PIL import Image
        except ImportError:
            self.stderr.write('Pillow not installed. Run: pip install Pillow')
            return

        dry     = options['dry_run']
        rethumb = options['rethumbnail']
        media   = Path(settings.MEDIA_ROOT)
        src     = media / 'arsip_foto'
        thumb_base = media / 'arsip_foto_thumbs'

        if not src.exists():
            self.stderr.write(f'{src} does not exist')
            return

        new_albums = new_fotos = skipped = errors = 0

        for folder in sorted(src.iterdir()):
            if not folder.is_dir():
                continue

            folder_name = folder.name
            if not dry:
                album, created = Album.objects.get_or_create(
                    folder_name=folder_name,
                    defaults={'name': folder_name},
                )
                if created:
                    new_albums += 1
            else:
                album = None

            album_thumb_dir = thumb_base / folder_name
            if not dry:
                album_thumb_dir.mkdir(parents=True, exist_ok=True)

            # recurse into all nested subdirs
            for media_path in sorted(folder.rglob('*')):
                if not media_path.is_file():
                    continue
                if media_path.suffix.lower() not in SUPPORTED:
                    continue

                rel_path = str(media_path.relative_to(media))
                is_vid   = media_path.suffix.lower() in VIDEO_EXTENSIONS

                if not rethumb and Foto.objects.filter(file_path=rel_path).exists():
                    skipped += 1
                    continue

                # thumbnail — images via Pillow, videos via ffmpeg if available
                thumb_rel = ''
                w = h = 0
                if is_vid and not dry and __import__('shutil').which('ffmpeg'):
                    import subprocess as _sp
                    thumb_rel = f'arsip_foto_thumbs/{folder_name}/{media_path.stem}.jpg'
                    thumb_abs = media / thumb_rel
                    thumb_abs.parent.mkdir(parents=True, exist_ok=True)
                    dur_r = _sp.run(
                        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                         '-of', 'default=noprint_wrappers=1:nokey=1', str(media_path)],
                        capture_output=True, text=True)
                    try:
                        seek = max(1, round(float(dur_r.stdout.strip()) * 0.2))
                    except ValueError:
                        seek = 5
                    r = _sp.run(
                        ['ffmpeg', '-y', '-ss', str(seek), '-i', str(media_path),
                         '-vframes', '1',
                         '-vf', 'scale=220x220:force_original_aspect_ratio=decrease,'
                                'pad=220:220:(ow-iw)/2:(oh-ih)/2:black',
                         '-q:v', '3', str(thumb_abs)],
                        capture_output=True)
                    if r.returncode != 0 or not thumb_abs.exists():
                        thumb_rel = ''
                if not is_vid and not dry:
                    thumb_rel = f'arsip_foto_thumbs/{folder_name}/{media_path.stem}.jpg'
                    thumb_abs = media / thumb_rel
                    try:
                        with Image.open(media_path) as im:
                            im = im.convert('RGB')
                            w, h = im.size
                            im.thumbnail(THUMB_SIZE, Image.LANCZOS)
                            thumb_abs.parent.mkdir(parents=True, exist_ok=True)
                            im.save(thumb_abs, 'JPEG', quality=82)
                    except Exception as e:
                        self.stderr.write(f'  thumb error {media_path.name}: {e}')
                        thumb_rel = ''
                        errors += 1

                # EXIF date (images only)
                taken_at = None
                if not is_vid:
                    try:
                        from PIL import Image as _Im
                        with _Im.open(media_path) as im:
                            exif = im._getexif()
                            if exif:
                                raw = exif.get(36867) or exif.get(36868)
                                if raw:
                                    naive = datetime.datetime.strptime(raw, '%Y:%m:%d %H:%M:%S')
                                    taken_at = tz.make_aware(naive, datetime.timezone.utc)
                    except Exception:
                        pass

                if not dry:
                    obj, foto_created = Foto.objects.update_or_create(
                        file_path=rel_path,
                        defaults=dict(
                            album=album,
                            thumbnail_path=thumb_rel,
                            caption=media_path.stem.replace('_', ' '),
                            taken_at=taken_at,
                            file_size=min(media_path.stat().st_size, 2_147_483_647),
                            width=w,
                            height=h,
                            is_video=is_vid,
                        ),
                    )
                    if foto_created:
                        new_fotos += 1
                else:
                    new_fotos += 1

                if (new_fotos + skipped) % 500 == 0 and (new_fotos + skipped) > 0:
                    self.stdout.write(f'  processed {new_fotos + skipped} so far…')

            # set cover to first image (not video)
            if not dry and album and not album.cover_photo_id:
                first = album.fotos.filter(is_video=False).first()
                if not first:
                    first = album.fotos.first()
                if first:
                    album.cover_photo = first
                    album.save(update_fields=['cover_photo'])

        self.stdout.write(self.style.SUCCESS(
            f'Done — albums: {new_albums}, new fotos: {new_fotos}, skipped: {skipped}, errors: {errors}'
        ))
