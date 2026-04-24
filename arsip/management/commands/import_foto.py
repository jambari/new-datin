import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from arsip.models import Album, Foto

SUPPORTED = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
THUMB_SIZE = (220, 220)


class Command(BaseCommand):
    help = 'Scan media/arsip_foto/ and import photos into the database with thumbnails'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Report counts without writing to DB')
        parser.add_argument('--rethumbnail', action='store_true', help='Regenerate thumbnails for existing records')

    def handle(self, *args, **options):
        try:
            from PIL import Image
        except ImportError:
            self.stderr.write('Pillow not installed. Run: pip install Pillow')
            return

        dry   = options['dry_run']
        rethumb = options['rethumbnail']
        media = Path(settings.MEDIA_ROOT)
        src   = media / 'arsip_foto'
        thumb_base = media / 'arsip_foto_thumbs'

        if not src.exists():
            self.stderr.write(f'{src} does not exist — run rsync first')
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
                created = False
                album = None

            album_thumb_dir = thumb_base / folder_name
            if not dry:
                album_thumb_dir.mkdir(parents=True, exist_ok=True)

            for img_path in sorted(folder.rglob('*')):
                if img_path.suffix.lower() not in SUPPORTED:
                    continue

                rel_path = str(img_path.relative_to(media))

                if not rethumb and Foto.objects.filter(file_path=rel_path).exists():
                    skipped += 1
                    continue

                # --- thumbnail ---
                thumb_rel = f'arsip_foto_thumbs/{folder_name}/{img_path.stem}.jpg'
                thumb_abs = media / thumb_rel
                w = h = 0
                if not dry:
                    try:
                        with Image.open(img_path) as im:
                            im = im.convert('RGB')
                            w, h = im.size
                            im.thumbnail(THUMB_SIZE, Image.LANCZOS)
                            thumb_abs.parent.mkdir(parents=True, exist_ok=True)
                            im.save(thumb_abs, 'JPEG', quality=82)
                    except Exception as e:
                        self.stderr.write(f'  thumb error {img_path.name}: {e}')
                        thumb_rel = ''
                        errors += 1

                # --- EXIF date ---
                taken_at = None
                try:
                    with Image.open(img_path) as im:
                        exif = im._getexif()
                        if exif:
                            raw = exif.get(36867) or exif.get(36868)
                            if raw:
                                taken_at = datetime.datetime.strptime(raw, '%Y:%m:%d %H:%M:%S')
                except Exception:
                    pass

                if not dry:
                    obj, foto_created = Foto.objects.update_or_create(
                        file_path=rel_path,
                        defaults=dict(
                            album=album,
                            thumbnail_path=thumb_rel,
                            taken_at=taken_at,
                            file_size=img_path.stat().st_size,
                            width=w,
                            height=h,
                        ),
                    )
                    if foto_created:
                        new_fotos += 1
                else:
                    new_fotos += 1

                if (new_fotos + skipped) % 200 == 0:
                    self.stdout.write(f'  processed {new_fotos + skipped} so far…')

            # set cover photo
            if not dry and album and not album.cover_photo_id:
                first = album.fotos.first()
                if first:
                    album.cover_photo = first
                    album.save(update_fields=['cover_photo'])

        self.stdout.write(self.style.SUCCESS(
            f'Done — albums: {new_albums}, new fotos: {new_fotos}, skipped: {skipped}, errors: {errors}'
        ))
