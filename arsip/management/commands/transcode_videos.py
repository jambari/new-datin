"""
Transcode HEVC/H.265 videos to H.264 so browsers can play them inline.
Replaces the original file in-place (original is deleted after successful transcode).

Usage:
  python manage.py transcode_videos          # transcode all videos in arsip_foto/
  python manage.py transcode_videos --dry-run
"""
import subprocess
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from arsip.models import Foto, VIDEO_EXTENSIONS


class Command(BaseCommand):
    help = 'Transcode HEVC/H.265 videos to H.264 for browser compatibility'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        if not shutil.which('ffmpeg'):
            self.stderr.write('ffmpeg not found. Install with: sudo apt install ffmpeg')
            return

        dry  = options['dry_run']
        media = Path(settings.MEDIA_ROOT)
        done = skipped = errors = 0

        videos = Foto.objects.filter(is_video=True)
        self.stdout.write(f'Found {videos.count()} video records')

        for foto in videos:
            src = media / foto.file_path
            if not src.exists():
                continue

            # Check codec — skip if already H.264
            probe = subprocess.run(
                ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                 '-show_entries', 'stream=codec_name', '-of', 'default=noprint_wrappers=1:nokey=1',
                 str(src)],
                capture_output=True, text=True
            )
            codec = probe.stdout.strip().lower()
            if codec in ('h264', 'avc'):
                skipped += 1
                continue

            self.stdout.write(f'  [{codec}] {src.name}')
            if dry:
                done += 1
                continue

            tmp = src.with_suffix('.h264_tmp.mp4')
            result = subprocess.run(
                ['ffmpeg', '-y', '-i', str(src),
                 '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                 '-c:a', 'aac', '-b:a', '128k',
                 '-movflags', '+faststart',
                 str(tmp)],
                capture_output=True
            )
            if result.returncode == 0 and tmp.exists():
                src.unlink()
                tmp.rename(src)
                done += 1
            else:
                self.stderr.write(f'  ERROR: {src.name}')
                tmp.unlink(missing_ok=True)
                errors += 1

        self.stdout.write(self.style.SUCCESS(
            f'Done — transcoded: {done}, already H.264 (skipped): {skipped}, errors: {errors}'
        ))
