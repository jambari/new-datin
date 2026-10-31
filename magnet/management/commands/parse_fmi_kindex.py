from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from magnet.fmi_kindex import FmiLayoutError, fmi_start_date, update_kindex_from_image
from magnet.models import FmiIndicesImage, KIndexDaily


class Command(BaseCommand):
    help = ("Urai ulang nilai indeks K dari citra FMI K yang sudah tersimpan (urut waktu unduh, "
            "yang terbaru menimpa) ke KIndexDaily mulai KINDEX_FMI_START. Citra dengan ETag "
            "sama dengan citra sebelumnya (sumber belum diperbarui) dilewati.")

    def add_arguments(self, parser):
        parser.add_argument("--since", help="Hanya citra bertanggal sejak YYYY-MM-DD")
        parser.add_argument("--reset", action="store_true",
                            help="Hapus dulu semua baris KIndexDaily bersumber FMI lalu bangun ulang")
        parser.add_argument("--dry-run", action="store_true",
                            help="Tampilkan hasil tanpa menyimpan ke database")

    def handle(self, *args, **options):
        if options["reset"] and options["since"]:
            raise CommandError("--reset membangun ulang semua hari; jangan dipakai bersama --since")
        qs = FmiIndicesImage.objects.filter(jenis=FmiIndicesImage.K).order_by("updated_at")
        if options["since"]:
            try:
                qs = qs.filter(tanggal__gte=datetime.strptime(options["since"], "%Y-%m-%d").date())
            except ValueError:
                raise CommandError("Format --since harus YYYY-MM-DD")
        self.stdout.write(f"Batas sumber FMI: {fmi_start_date():%d/%m/%Y}; {qs.count()} citra K.")

        with transaction.atomic():
            if options["reset"]:
                deleted, _ = KIndexDaily.objects.filter(sumber=KIndexDaily.SUMBER_FMI).delete()
                self.stdout.write(f"  {deleted} baris indeks K bersumber FMI dihapus.")
            touched, failed, seen = set(), 0, set()
            for img in qs:
                if img.etag and img.etag in seen:
                    self.stdout.write(f"  {img.filename}: dilewati — citra sumber sama dengan sebelumnya")
                    continue
                seen.add(img.etag)
                try:
                    days = update_kindex_from_image(img)
                except (FmiLayoutError, OSError, ValueError) as exc:
                    failed += 1
                    self.stderr.write(self.style.WARNING(f"  {img.filename}: gagal — {exc}"))
                    continue
                touched.update(days)
                self.stdout.write(f"  {img.filename}: {len(days)} hari")

            if options["dry_run"]:
                for row in KIndexDaily.objects.filter(tanggal__in=touched).order_by("tanggal"):
                    self.stdout.write(f"    {row.tanggal}: {row.k_values}")
                transaction.set_rollback(True)

        msg = f"Selesai: {len(touched)} hari indeks K dari citra FMI"
        if touched:
            msg += f" ({min(touched):%d/%m/%Y} s.d. {max(touched):%d/%m/%Y})"
        msg += f", {failed} citra gagal." if failed else "."
        if options["dry_run"]:
            msg += " (dry-run, tidak disimpan)"
        self.stdout.write(self.style.SUCCESS(msg))
