import re
import requests
from datetime import timezone, timedelta, datetime
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from repository.models import FeltEarthquake, ShakemapEvent

SHAKEMAP_URL = "https://static.bmkg.go.id/{wib_ts}.mmi.jpg"
GCS_BASE_URL = "https://bmkg-content-inatews.storage.googleapis.com/{wib_ts}_rev/{filename}"

WIB = timezone(timedelta(hours=7))
UTC = timezone.utc

GCS_FIELDS = [
    ("img_stationlist", "stationlist_MMI.jpg"),
    ("img_impact_list", "impact_list.jpg"),
    ("img_loc_map",     "loc_map.png"),
    ("img_report_1",    "reports-1.jpg"),
    ("img_report_2",    "reports-2.jpg"),
]


_TS_RE = re.compile(r'(\d{14})')

def extract_wib_ts(event_id):
    """
    Extract the 14-digit WIB timestamp from a ShakemapEvent event_id.
    Handles both pure '20260421014706' and legacy '20240430024335_35_-2570_...' formats.
    Returns the 14-digit string or None if not found.
    """
    m = _TS_RE.match(event_id)
    return m.group(1) if m else None


def wib_ts_to_utc(wib_ts):
    """Parse yyyymmddHHMMSS WIB string → UTC datetime."""
    dt_wib = datetime.strptime(wib_ts, "%Y%m%d%H%M%S").replace(tzinfo=WIB)
    return dt_wib.astimezone(UTC)


def fetch_image(url):
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200 and resp.headers.get("Content-Type", "").startswith("image/"):
            return resp.content
    except Exception:
        pass
    return None


class Command(BaseCommand):
    help = (
        "Seed FeltEarthquake from ShakemapEvent records, then backfill "
        "all missing images from BMKG GCS and static servers."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Preview without saving anything.")
        parser.add_argument("--force", action="store_true",
                            help="Re-download images even if already saved.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        force   = options["force"]

        shakemap_qs = ShakemapEvent.objects.all().order_by("event_time")
        total = shakemap_qs.count()
        self.stdout.write(f"Found {total} ShakemapEvent records to process.\n")

        created_count = img_updated = skipped = errors = 0

        for shk in shakemap_qs:
            # --- 0. Extract clean 14-digit WIB timestamp ---
            wib_ts = extract_wib_ts(shk.event_id)
            if not wib_ts:
                self.stdout.write(self.style.WARNING(f"  Skipping unrecognised event_id: {shk.event_id}"))
                skipped += 1
                continue

            label = f"M{shk.magnitude} {shk.location_string[:40]} ({wib_ts})"

            # --- 1. Ensure FeltEarthquake exists ---
            try:
                event_dt_utc = wib_ts_to_utc(wib_ts)
            except ValueError:
                self.stderr.write(f"  Skipping bad timestamp: {wib_ts}")
                errors += 1
                continue

            if not dry_run:
                fe, created = FeltEarthquake.objects.get_or_create(
                    event_datetime=event_dt_utc,
                    defaults={
                        "latitude":  shk.latitude,
                        "longitude": shk.longitude,
                        "magnitude": shk.magnitude,
                        "depth_km":  shk.depth,
                        "wilayah":   shk.location_string,
                        "dirasakan": "",
                    },
                )
                if created:
                    created_count += 1
                    self.stdout.write(self.style.SUCCESS(f"  [NEW FeltEarthquake] {label}"))
            else:
                created = False
                fe = None

            # --- 2. GCS images ---
            gcs_changed = False
            for field_name, filename in GCS_FIELDS:
                if fe and getattr(fe, field_name) and not force:
                    continue
                url       = GCS_BASE_URL.format(wib_ts=wib_ts, filename=filename)
                img_bytes = fetch_image(url)
                if img_bytes:
                    if not dry_run and fe:
                        getattr(fe, field_name).save(
                            f"{wib_ts}_{filename}", ContentFile(img_bytes), save=False
                        )
                    self.stdout.write(self.style.SUCCESS(f"  [{field_name}] OK — {label}"))
                    gcs_changed = True
                # silently skip missing images (404 is normal for some fields)

            if gcs_changed and not dry_run and fe:
                try:
                    fe.save()
                    img_updated += 1
                except Exception as e:
                    self.stderr.write(f"  SAVE ERROR: {e} — {label}")
                    errors += 1
            elif not gcs_changed and not created:
                skipped += 1

            # --- 3. MMI shakemap on ShakemapEvent ---
            if not shk.shakemap_image or force:
                url       = SHAKEMAP_URL.format(wib_ts=wib_ts)
                img_bytes = fetch_image(url)
                if img_bytes:
                    if not dry_run:
                        shk.shakemap_image.save(
                            f"{wib_ts}.mmi.jpg", ContentFile(img_bytes), save=True
                        )
                    self.stdout.write(self.style.SUCCESS(f"  [shakemap_image] OK — {label}"))

        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"\n{prefix}Done. "
            f"FeltEarthquake created: {created_count} | "
            f"Images updated: {img_updated} | "
            f"Already complete: {skipped} | "
            f"Errors: {errors}"
        ))
