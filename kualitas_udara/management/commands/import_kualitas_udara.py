import csv
import os
from datetime import datetime

from django.core.management.base import BaseCommand

from kualitas_udara.models import KAHSeriesData, SPMSeriesData

KAH_FIELD_MAP = {
    "PH": "ph",
    "DH": "dh",
    "CA": "ca",
    "MG": "mg",
    "NA": "na",
    "K": "k",
    "NH4": "nh4",
    "CL": "cl",
    "SO4": "so4",
    "NO3": "no3",
    "KT": "kt",
    "AC": "ac",
    "AL": "al",
    "CH": "ch",
    "OX": "ox",
}


def parse_float(value):
    value = (value or "").strip()
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


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
        self.skip_existing = options["skip_existing"]
        self.import_kah(options["kah_path"])
        self.import_spm(options["spm_path"])

    def save_row(self, model, lookup, defaults):
        """Simpan satu baris; kembalikan 'created', 'updated' atau 'skipped'."""
        if self.skip_existing:
            if model.objects.filter(**lookup).exists():
                return "skipped"
            model.objects.create(**lookup, **defaults)
            return "created"
        _obj, was_created = model.objects.update_or_create(**lookup, defaults=defaults)
        return "created" if was_created else "updated"

    def report(self, label, counts):
        self.stdout.write(
            self.style.SUCCESS(
                f"{label} selesai: {counts['created']} data baru, {counts['updated']} data diperbarui, "
                f"{counts['skipped']} dilewati (sudah ada)."
            )
        )

    def import_kah(self, path):
        if not os.path.exists(path):
            self.stderr.write(self.style.WARNING(f"File KAH tidak ditemukan: {path}"))
            return

        counts = {"created": 0, "updated": 0, "skipped": 0}
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                bulan = (row.get("bulan") or "").strip()
                minggu = (row.get("minggu") or "").strip()
                stasiun = (row.get("stasiun") or "").strip()
                if not stasiun or not bulan or not minggu:
                    continue

                defaults = {
                    field_name: parse_float(row.get(csv_col))
                    for csv_col, field_name in KAH_FIELD_MAP.items()
                }
                lookup = {"stasiun": stasiun, "bulan": bulan, "minggu": minggu}
                counts[self.save_row(KAHSeriesData, lookup, defaults)] += 1

        self.report("KAH", counts)

    def import_spm(self, path):
        if not os.path.exists(path):
            self.stderr.write(self.style.WARNING(f"File SPM tidak ditemukan: {path}"))
            return

        counts = {"created": 0, "updated": 0, "skipped": 0}
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                stasiun = (row.get("stasiun") or "").strip()
                timestamp_raw = (row.get("timestamp") or "").strip()
                if not stasiun or not timestamp_raw:
                    continue
                try:
                    timestamp = datetime.strptime(timestamp_raw, "%Y-%m-%d").date()
                except ValueError:
                    self.stderr.write(
                        self.style.WARNING(f"Lewati baris SPM tanggal invalid: {timestamp_raw}")
                    )
                    continue

                lookup = {"stasiun": stasiun, "timestamp": timestamp}
                defaults = {"spm": parse_float(row.get("SPM"))}
                counts[self.save_row(SPMSeriesData, lookup, defaults)] += 1

        self.report("SPM", counts)
