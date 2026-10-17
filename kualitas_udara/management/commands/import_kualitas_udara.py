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

    def handle(self, *args, **options):
        self.import_kah(options["kah_path"])
        self.import_spm(options["spm_path"])

    def import_kah(self, path):
        if not os.path.exists(path):
            self.stderr.write(self.style.WARNING(f"File KAH tidak ditemukan: {path}"))
            return

        created = 0
        updated = 0
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                bulan = (row.get("bulan") or "").strip()
                minggu = (row.get("minggu") or "").strip()
                stasiun = (row.get("stasiun") or "").strip()
                if not stasiun or not bulan or not minggu:
                    continue

                defaults = {
                    "stasiun": stasiun,
                    "bulan": bulan,
                    "minggu": minggu,
                }
                for csv_col, field_name in KAH_FIELD_MAP.items():
                    defaults[field_name] = parse_float(row.get(csv_col))

                obj, was_created = KAHSeriesData.objects.update_or_create(
                    stasiun=stasiun,
                    bulan=bulan,
                    minggu=minggu,
                    defaults=defaults,
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"KAH selesai: {created} data baru, {updated} data diperbarui."
            )
        )

    def import_spm(self, path):
        if not os.path.exists(path):
            self.stderr.write(self.style.WARNING(f"File SPM tidak ditemukan: {path}"))
            return

        created = 0
        updated = 0
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

                obj, was_created = SPMSeriesData.objects.update_or_create(
                    stasiun=stasiun,
                    timestamp=timestamp,
                    defaults={
                        "stasiun": stasiun,
                        "timestamp": timestamp,
                        "spm": parse_float(row.get("SPM")),
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"SPM selesai: {created} data baru, {updated} data diperbarui."
            )
        )
