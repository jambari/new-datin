import os

from django.core.management.base import BaseCommand, CommandError

from magnet.kindex_import import import_kindex_workbook


class Command(BaseCommand):
    help = "Impor indeks K harian dari berkas Excel grafik_kindeks <tahun>.xlsx."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Lokasi berkas .xlsx")
        parser.add_argument("--tahun", type=int, required=True, help="Tahun data (judul sheet bisa keliru)")
        parser.add_argument("--bulan", type=int, nargs="*", help="Hanya bulan tertentu, mis. --bulan 1 2 3")

    def handle(self, *args, **options):
        path = options["path"]
        if not os.path.exists(path):
            raise CommandError(f"Berkas tidak ditemukan: {path}")
        with open(path, "rb") as f:
            summary, warnings = import_kindex_workbook(
                f, options["tahun"], os.path.basename(path), options["bulan"]
            )
        for w in warnings:
            self.stderr.write(self.style.WARNING(w))
        for bulan, c in summary.items():
            self.stdout.write(f"{bulan}: {c['data']} hari berdata, {c['kosong']} hari tanpa data")
        self.stdout.write(self.style.SUCCESS(f"Selesai: {len(summary)} bulan diimpor."))
