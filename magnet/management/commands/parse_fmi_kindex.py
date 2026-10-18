from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from magnet.fmi_kindex import FmiLayoutError, fmi_start_date, update_kindex_from_image
from magnet.models import FmiIndicesImage


class Command(BaseCommand):
    help = ("Urai ulang nilai indeks K dari citra FMI K yang sudah tersimpan (urut waktu unduh, "
            "yang terbaru menimpa) ke KIndexDaily mulai KINDEX_FMI_START.")

    def add_arguments(self, parser):
        parser.add_argument("--since", help="Hanya citra bertanggal sejak YYYY-MM-DD")

    def handle(self, *args, **options):
        qs = FmiIndicesImage.objects.filter(jenis=FmiIndicesImage.K).order_by("updated_at")
        if options["since"]:
            try:
                qs = qs.filter(tanggal__gte=datetime.strptime(options["since"], "%Y-%m-%d").date())
            except ValueError:
                raise CommandError("Format --since harus YYYY-MM-DD")
        self.stdout.write(f"Batas sumber FMI: {fmi_start_date():%d/%m/%Y}; {qs.count()} citra K.")
        touched, failed = set(), 0
        for img in qs:
            try:
                days = update_kindex_from_image(img)
            except (FmiLayoutError, OSError, ValueError) as exc:
                failed += 1
                self.stderr.write(self.style.WARNING(f"  {img.filename}: gagal — {exc}"))
                continue
            touched.update(days)
            self.stdout.write(f"  {img.filename}: {len(days)} hari")
        msg = f"Selesai: {len(touched)} hari indeks K dari citra FMI"
        if touched:
            msg += f" ({min(touched):%d/%m/%Y} s.d. {max(touched):%d/%m/%Y})"
        self.stdout.write(self.style.SUCCESS(msg + (f", {failed} citra gagal." if failed else ".")))
