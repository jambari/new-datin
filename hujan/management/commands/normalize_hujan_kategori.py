import json
import os
from collections import Counter
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from hujan.categories import normalize_kategori
from hujan.models import Hujan


class Command(BaseCommand):
    help = "Seragamkan penulisan kategori hujan lama ke nilai baku form (nilai lama dicadangkan ke JSON)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Tampilkan rencana perubahan tanpa menyimpan.")
        parser.add_argument("--backup", default=os.path.expanduser(
            f"~/backups/hujan_kategori_{datetime.now():%Y%m%d_%H%M%S}.json"))

    def handle(self, *args, **options):
        changes, unknown = [], Counter()
        for pk, raw in Hujan.objects.values_list("pk", "kategori"):
            key = normalize_kategori(raw)
            if key is None:
                unknown[raw] += 1
            elif key != (raw or ""):
                changes.append((pk, raw, key))
        plan = Counter((raw, key) for _pk, raw, key in changes)
        for (raw, key), n in plan.most_common():
            self.stdout.write(f"  {raw!r:28} -> {key!r:16} {n}")
        for raw, n in unknown.items():
            self.stderr.write(self.style.WARNING(f"  tidak dikenali, dibiarkan: {raw!r} ({n})"))
        if options["dry_run"]:
            self.stdout.write(f"[dry-run] {len(changes)} record akan diubah.")
            return
        if not changes:
            self.stdout.write("Tidak ada yang perlu diubah.")
            return
        os.makedirs(os.path.dirname(options["backup"]), exist_ok=True)
        with open(options["backup"], "w") as f:
            json.dump([{"pk": pk, "kategori": raw} for pk, raw, _key in changes], f)
        os.chmod(options["backup"], 0o600)
        with transaction.atomic():
            for pk, _raw, key in changes:
                Hujan.objects.filter(pk=pk).update(kategori=key)
        self.stdout.write(self.style.SUCCESS(f"{len(changes)} record diseragamkan; cadangan: {options['backup']}"))
