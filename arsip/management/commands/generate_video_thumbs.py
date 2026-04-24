"""
Generate thumbnail images from a frame at ~20% duration for all video Foto records.

Usage:
  python manage.py generate_video_thumbs          # only videos without thumbnails
  python manage.py generate_video_thumbs --force  # regenerate all video thumbnails
"""
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from arsip.models import Foto

THUMB_SIZE = '220x220'  # ffmpeg scale filter (keeps aspect, pads to fit)


def get_duration(src):
    r = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'default=noprint_wrappers=1:nokey=1', str(src)],
        capture_output=True, text=True
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def extract_thumb(src, thumb_abs, seek_sec):
    thumb_abs.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ['ffmpeg', '-y', '-ss', str(seek_sec), '-i', str(src),
         '-vframes', '1',
         '-vf', f'scale={THUMB_SIZE}:force_original_aspect_ratio=decrease,'
                f'pad={THUMB_SIZE}:(ow-iw)/2:(oh-ih)/2:black',
         '-q:v', '3', str(thumb_abs)],
        capture_output=True
    )
    return r.returncode == 0 and thumb_abs.exists()


class Command(BaseCommand):
    help = 'Generate thumbnails for video files using ffmpeg'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help='Regenerate even if thumbnail already exists')

    def handle(self, *args, **options):
        force = options['force']
        media = Path(settings.MEDIA_ROOT)
        done = skipped = errors = 0

        qs = Foto.objects.filter(is_video=True)
        if not force:
            qs = qs.filter(thumbnail_path='')

        total = qs.count()
        self.stdout.write(f'Generating thumbnails for {total} videos…')

        for foto in qs.iterator():
            src = media / foto.file_path
            if not src.exists():
                errors += 1
                continue

            duration = get_duration(src)
            seek = max(1, round((duration or 10) * 0.2))

            thumb_rel  = f'arsip_foto_thumbs/{foto.album.folder_name}/{src.stem}.jpg'
            thumb_abs  = media / thumb_rel

            if extract_thumb(src, thumb_abs, seek):
                foto.thumbnail_path = thumb_rel
                foto.save(update_fields=['thumbnail_path'])
                done += 1
                if done % 50 == 0:
                    self.stdout.write(f'  {done}/{total} done…')
            else:
                self.stderr.write(f'  ERROR: {src.name}')
                errors += 1

        self.stdout.write(self.style.SUCCESS(
            f'Done — thumbnails generated: {done}, skipped: {skipped}, errors: {errors}'
        ))
