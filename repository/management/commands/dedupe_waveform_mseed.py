"""Bersihkan salinan .mseed ganda di media/event_waveforms/ akibat PUSH ulang dari .50.

Sebelum perbaikan ingest_pushed_event, tiap PUSH menyimpan .mseed lewat FileField.save(), sehingga
Django menambah salinan bersufiks acak (STA_COMP_Ab3xYz9.mseed) dan salinan lama tertinggal.

Langkah:
  1. Tiap EventStationWaveform yang .mseed-nya bukan di path tetap
     (event_waveforms/<event_id>/<STA>_<COMP>.mseed) dipindah ke path tetap itu.
  2. Berkas bersufiks di event_waveforms/ yang tidak dirujuk baris mana pun DAN punya berkas
     path-tetap di sebelahnya dihapus. Berkas lain tidak disentuh.

Bawaan hanya menampilkan rencana; tambahkan --apply untuk menjalankan.

    python manage.py dedupe_waveform_mseed            # rencana
    python manage.py dedupe_waveform_mseed --apply
"""
import os
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from repository.models import EventStationWaveform, _waveform_mseed_path

_SUFFIXED = re.compile(r"^(?P<base>.+)_[A-Za-z0-9]{7}\.mseed$")


class Command(BaseCommand):
    help = "Hapus salinan .mseed bersufiks acak di media/event_waveforms/ (bawaan: hanya rencana)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Jalankan (tanpa ini hanya rencana).")

    def handle(self, *args, **opts):
        apply = opts["apply"]
        media = Path(settings.MEDIA_ROOT)
        moved = missing = 0
        targets = set()                                   # path tetap yang diisi langkah 1

        # 1) Baris yang menunjuk salinan bersufiks → path tetap.
        for obj in EventStationWaveform.objects.exclude(mseed="").exclude(mseed__isnull=True).iterator():
            rel = _waveform_mseed_path(obj, "")
            if obj.mseed.name == rel:
                continue
            src = media / obj.mseed.name
            if not src.exists():
                missing += 1
                continue
            moved += 1
            targets.add(rel)
            if apply:
                dest = media / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                os.replace(src, dest)
                obj.mseed.name = rel
                obj.save(update_fields=["mseed"])

        # 2) Salinan bersufiks yang tidak dirujuk dan punya berkas path-tetap.
        referenced = set(EventStationWaveform.objects.exclude(mseed="").exclude(mseed__isnull=True)
                         .values_list("mseed", flat=True))
        root = media / "event_waveforms"
        doomed, freed = [], 0
        if root.is_dir():
            for path in root.rglob("*.mseed"):
                m = _SUFFIXED.match(path.name)
                if not m:
                    continue
                rel = str(path.relative_to(media))
                canonical = path.with_name(m.group("base") + ".mseed")
                has_canonical = canonical.exists() or str(canonical.relative_to(media)) in targets
                if rel in referenced or not has_canonical:
                    continue
                doomed.append(path)
                freed += path.stat().st_size

        for path in doomed:
            if apply:
                path.unlink(missing_ok=True)

        verb = "dipindah" if apply else "akan dipindah"
        verb2 = "dihapus" if apply else "akan dihapus"
        self.stdout.write(f"Baris ke path tetap: {moved} {verb} ({missing} berkas hilang, dilewati).")
        self.stdout.write(f"Salinan ganda: {len(doomed)} {verb2}, {freed / 1e6:.1f} MB.")
        if not apply:
            self.stdout.write("Rencana saja. Jalankan dengan --apply untuk menerapkan.")
