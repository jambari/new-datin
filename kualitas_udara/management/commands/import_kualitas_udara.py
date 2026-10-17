import os

from django.core.management.base import BaseCommand, CommandError

from kualitas_udara.importer import CSVFormatError, import_kah, import_spm


class Command(BaseCommand):
    help = "Impor data KAH dan SPM dari file CSV ke model kualitas_udara."

    def add_arguments(self, parser):
        parser.add_argument(
            "--kah",
            dest="kah_path",
            default=os.path.expanduser("~/Documents/bukti-skp/kah_series_data.csv"),
            help="Lokasi file kah_series_data.csv",
        )
        parser.add_argument(
            "--spm",
            dest="spm_path",
            default=os.path.expanduser("~/Documents/bukti-skp/spm_series_data.csv"),
            help="Lokasi file spm_series_data.csv",
        )
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            help="Lewati data yang sudah ada di database (tidak ditimpa); hanya data baru yang diimpor.",
        )

    def handle(self, *args, **options):
        for label, path, importer in (
            ("KAH", options["kah_path"], import_kah),
            ("SPM", options["spm_path"], import_spm),
        ):
            if not os.path.exists(path):
                self.stderr.write(self.style.WARNING(f"File {label} tidak ditemukan: {path}"))
                continue
            with open(path, newline="", encoding="utf-8") as f:
                try:
                    counts = importer(f, skip_existing=options["skip_existing"])
                except CSVFormatError as exc:
                    raise CommandError(str(exc))
            self.stdout.write(
                self.style.SUCCESS(
                    f"{label} selesai: {counts['created']} data baru, {counts['updated']} data diperbarui, "
                    f"{counts['skipped']} dilewati (sudah ada), {counts['invalid']} baris tidak valid."
                )
            )
