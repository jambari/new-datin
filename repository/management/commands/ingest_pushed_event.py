"""Ingest files pushed from .50 (sysop@172.21.63.50) into new-datin DB rows.

The .50 ShakeMap manager's "PUSH" button rsyncs:
    intensity_MMI.jpg -> /var/www/html/media/shakemaps/<WIB>.mmi.jpg
    .psa5             -> /var/www/html/media/event_response_spectra/<WIB>/*.psa5
    waveform PNGs     -> /var/www/html/media/event_waveforms/<WIB>/<sta>_<comp>.png
    raw .mseed        -> /var/www/html/media/waveforms/<WIB>/*.mseed   (kept for reference)

This command picks those files up and links them to DB rows. Idempotent: re-running
upserts (object.shakemap_image is rewritten; spectrum / waveform rows are
update_or_create on (event_id, station_code, component)).

Usage:
    python manage.py ingest_pushed_event 20260522071031
    python manage.py ingest_pushed_event 20260522071031 --quiet   # JSON summary only
"""
import json
import os
import re
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from repository.models import (
    EventResponseSpectrum, EventStationWaveform, ShakemapEvent,
)

# Filename patterns produced by scwfparam on .50:
#   <WIB>_IA_<STA>_<COMP>_BP4_0.1_40.psa5
#   <WIB>_IA_<STA>_<COMP>_BP4_0.1_40.mseed
# Waveform PNG (rendered on .50): <STA>_<COMP>.png
_PSA5_RE = re.compile(r"^\d{14}_(?P<net>[A-Z0-9]+)_(?P<sta>[A-Z0-9]+)_(?P<comp>[A-Z0-9]+)_BP[\d.]+_[\d.]+_[\d.]+\.psa5$")
_PNG_RE  = re.compile(r"^(?P<sta>[A-Z0-9]+)_(?P<comp>[A-Z0-9]+)\.png$")


def _parse_psa5(text):
    """Return [{"T": period_s, "Sa": value_g}, …]. Skips comment lines / blanks."""
    pts = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            pts.append({"T": float(parts[0]), "Sa": float(parts[1])})
        except ValueError:
            continue
    return pts


class Command(BaseCommand):
    help = (
        "Link files pushed from .50 into ShakemapEvent / EventResponseSpectrum / "
        "EventStationWaveform DB rows."
    )

    def add_arguments(self, parser):
        parser.add_argument("wib_ts", help="14-digit WIB timestamp (e.g. 20260522071031)")
        parser.add_argument("--quiet", action="store_true",
                            help="Suppress per-file output; print only the JSON summary at the end.")

    def handle(self, *args, **options):
        wib = options["wib_ts"].strip()
        if not (len(wib) == 14 and wib.isdigit()):
            raise CommandError("wib_ts must be a 14-digit YYYYMMDDhhmmss string")
        quiet = options["quiet"]

        media = Path(settings.MEDIA_ROOT)
        intensity_path = media / "shakemaps" / ("%s.mmi.jpg" % wib)
        psa5_dir       = media / "event_response_spectra" / wib
        wf_png_dir     = media / "event_waveforms" / wib

        summary = {
            "wib_ts": wib,
            "intensity_linked": False,
            "shakemap_event_existed": False,
            "psa5_upserted": 0,
            "waveform_upserted": 0,
            "errors": [],
        }

        # ---- 1) Link intensity image into ShakemapEvent.shakemap_image ----
        # Point the field at the rsync'd path directly (no re-save) so repeat
        # pushes don't leave Django-renamed duplicates (e.g. _IzbL2GH suffixes).
        if intensity_path.exists():
            from datetime import datetime as _dt, timezone as _tz
            shk = ShakemapEvent.objects.filter(event_id=wib).first()
            if shk is None:
                # Auto-create the ShakemapEvent from the WIB timestamp
                try:
                    dt = _dt.strptime(wib, "%Y%m%d%H%M%S").replace(tzinfo=_tz.utc)
                    shk = ShakemapEvent.objects.create(
                        event_id=wib,
                        event_time=dt,
                        latitude=0.0, longitude=0.0,
                        magnitude=0.0, depth=0.0,
                        location_string="Pushed from jaygenerator (auto-created)",
                    )
                    summary["shakemap_event_created"] = True
                    if not quiet:
                        self.stdout.write(f"  Created ShakemapEvent(event_id={wib}) from push data")
                except Exception as e:
                    summary["errors"].append(
                        "Failed to auto-create ShakemapEvent(%s): %s" % (wib, e)
                    )
            if shk is not None:
                summary["shakemap_event_existed"] = True
                rel = str(intensity_path.relative_to(media))   # e.g. "shakemaps/20260522071031.mmi.jpg"
                # Clean up any prior Django-renamed copies (foo_xxxxxx.mmi.jpg) that
                # came from earlier saves before this fix.
                prior = shk.shakemap_image.name if shk.shakemap_image else None
                if prior and prior != rel:
                    try:
                        (media / prior).unlink(missing_ok=True)
                    except OSError:
                        pass
                shk.shakemap_image.name = rel
                shk.save(update_fields=["shakemap_image"])
                summary["intensity_linked"] = True
                if not quiet:
                    self.stdout.write(self.style.SUCCESS(
                        "  intensity linked: ShakemapEvent.event_id=%s  ->  %s" % (wib, rel)))
        else:
            if not quiet:
                self.stdout.write("  no intensity image at %s — skipping" % intensity_path)

        # ---- 2) Upsert EventResponseSpectrum rows from .psa5 ----
        if psa5_dir.is_dir():
            for f in sorted(psa5_dir.iterdir()):
                m = _PSA5_RE.match(f.name)
                if not m:
                    continue
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                except OSError as e:
                    summary["errors"].append("read %s: %s" % (f.name, e))
                    continue
                pts = _parse_psa5(text)
                if not pts:
                    summary["errors"].append("parse %s: no usable data rows" % f.name)
                    continue
                EventResponseSpectrum.objects.update_or_create(
                    event_id=wib,
                    station_code=m.group("sta"),
                    component=m.group("comp"),
                    defaults={"spectrum": pts},
                )
                summary["psa5_upserted"] += 1
                if not quiet:
                    self.stdout.write("  psa5: %s/%s (%d pts)"
                                      % (m.group("sta"), m.group("comp"), len(pts)))
        else:
            if not quiet:
                self.stdout.write("  no psa5 dir at %s — skipping" % psa5_dir)

        # ---- 3) Upsert EventStationWaveform rows from PNG plots ----
        # Point .image at the rsync'd path (no re-save), same idempotency fix as #1.
        if wf_png_dir.is_dir():
            for f in sorted(wf_png_dir.iterdir()):
                m = _PNG_RE.match(f.name)
                if not m:
                    continue
                rel = str(f.relative_to(media))
                obj, _ = EventStationWaveform.objects.update_or_create(
                    event_id=wib,
                    station_code=m.group("sta"),
                    component=m.group("comp"),
                    defaults={},
                )
                prior = obj.image.name if obj.image else None
                if prior and prior != rel:
                    try:
                        (media / prior).unlink(missing_ok=True)
                    except OSError:
                        pass
                obj.image.name = rel
                obj.save(update_fields=["image"])
                summary["waveform_upserted"] += 1
                if not quiet:
                    self.stdout.write("  waveform: %s/%s"
                                      % (m.group("sta"), m.group("comp")))
        else:
            if not quiet:
                self.stdout.write("  no waveform PNG dir at %s — skipping" % wf_png_dir)

        # ---- 4) Link .mseed files into EventStationWaveform.mseed ----
        # rsync'd to: /var/www/html/media/waveforms/<WIB>/<sta>_<comp>.mseed
        wf_mseed_dir = media / "waveforms" / wib
        if wf_mseed_dir.is_dir():
            # Filename format from pipeline: <WIB>_IA_<STA>_<COMP>_BP4_0.1_40.mseed
            # or simpler: <STA>_<COMP>.mseed from manual uploads
            _MSEED_RE = re.compile(r"^(?:\d{14}_[A-Z0-9]+_)?(?P<sta>[A-Z0-9]+)_(?P<comp>[A-Z0-9]+(?:_[A-Z0-9]+)?)(?:_BP[\d.]+_[\d.]+_[\d.]+)?\.mseed$")
            for f in sorted(wf_mseed_dir.iterdir()):
                if not f.name.endswith(".mseed"):
                    continue
                m = _MSEED_RE.match(f.name)
                if not m:
                    if not quiet:
                        self.stdout.write(f"  skip mseed (no match): {f.name}")
                    continue
                obj, _ = EventStationWaveform.objects.update_or_create(
                    event_id=wib,
                    station_code=m.group("sta"),
                    component=m.group("comp"),
                    defaults={},
                )
                # Copy mseed file into Django storage
                from django.core.files import File
                with open(f, "rb") as fh:
                    obj.mseed.save(f"{m.group('sta')}_{m.group('comp')}.mseed", File(fh), save=True)
                if not quiet:
                    self.stdout.write(f"  mseed: {m.group('sta')}/{m.group('comp')}")
        else:
            if not quiet:
                self.stdout.write(f"  no mseed dir at {wf_mseed_dir} — skipping")

        # ---- Final summary (parsed by the .50 push endpoint) ----
        self.stdout.write("INGEST_SUMMARY " + json.dumps(summary))
