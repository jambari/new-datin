import datetime

from django.core.management.base import BaseCommand, CommandError

from magnet.kindex_fmi import compute_day, store_day


class Command(BaseCommand):
    help = ("Hitung indeks K JYP metode FMI dari data mentah LEMI (LEMI_RAW_DIR) dan simpan ke "
            "KIndexDaily (sumber lokal). Hari data Excel tidak disentuh.")

    def add_arguments(self, parser):
        parser.add_argument("--start", help="Tanggal UTC awal YYYY-MM-DD (default: kemarin lusa)")
        parser.add_argument("--end", help="Tanggal UTC akhir YYYY-MM-DD (default: hari ini)")
        parser.add_argument("--l9", type=float, help="Batas bawah K9 (nT); default KINDEX_JYP_L9")
        parser.add_argument("--dry-run", action="store_true", help="Tampilkan hasil tanpa menyimpan")

    def handle(self, *args, **options):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        try:
            start = datetime.date.fromisoformat(options["start"]) if options["start"] else today - datetime.timedelta(days=2)
            end = datetime.date.fromisoformat(options["end"]) if options["end"] else today
        except ValueError:
            raise CommandError("Format tanggal harus YYYY-MM-DD")
        day, stored = start, 0
        while day <= min(end, today):
            if options["dry_run"]:
                result, obj = compute_day(day, l9=options["l9"]), None
            else:
                result, obj = store_day(day, l9=options["l9"])
                stored += obj is not None
            flags = []
            if result["provisional"]:
                flags.append("sementara")
            if result["steps"]:
                flags.append(f"{result['steps']} loncatan dikoreksi")
            if not result["files"]:
                flags.append("tidak ada data mentah")
            ks = " ".join("-" if k is None else str(k) for k in result["k_values"])
            self.stdout.write(f"  {day}: {ks}" + (f"  ({', '.join(flags)})" if flags else ""))
            day += datetime.timedelta(days=1)
        if not options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"Selesai: {stored} hari disimpan."))
