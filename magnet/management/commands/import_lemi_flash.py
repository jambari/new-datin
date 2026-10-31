import datetime

from django.conf import settings
from django.core.management.base import BaseCommand

from magnet.fmi_kindex import fmi_start_date
from magnet.kindex_fmi import store_day
from magnet.lemi_flash import fill_day, read_flash


class Command(BaseCommand):
    help = ("Isi celah data LEMI dari salinan kartu CF logger (L018_*.B81). Hanya detik yang belum "
            "ada di LEMI_RAW_DIR yang ditulis, lalu indeks K hari terkait dihitung ulang.")

    def add_arguments(self, parser):
        parser.add_argument("files", nargs="+", help="Berkas .B81")
        parser.add_argument("--dry-run", action="store_true", help="Hanya laporkan yang akan diisi")

    def handle(self, *args, **options):
        merged = {}
        for path in options["files"]:
            for day, records in read_flash(path).items():
                merged.setdefault(day, {}).update(records)
        settings.LEMI_RAW_DIR.mkdir(parents=True, exist_ok=True)
        touched = set()
        for day in sorted(merged):
            added = fill_day(settings.LEMI_RAW_DIR, day, merged[day], dry_run=options["dry_run"])
            self.stdout.write(f"  {day}: {len(merged[day])} detik di kartu, {added} mengisi celah")
            if added:
                touched.update(day + datetime.timedelta(days=d) for d in (-1, 0, 1))
        if options["dry_run"]:
            return
        today = datetime.datetime.now(datetime.timezone.utc).date()
        for day in sorted(d for d in touched if fmi_start_date() <= d <= today):
            _, obj = store_day(day)
            if obj is not None:
                self.stdout.write(f"  K {day}: {obj.k_values}")
        self.stdout.write(self.style.SUCCESS(f"Selesai: {len(touched)} hari dihitung ulang."))
