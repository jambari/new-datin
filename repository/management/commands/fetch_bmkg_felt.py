import requests
from datetime import datetime, timezone, timedelta
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from repository.models import FeltEarthquake, ShakemapEvent

BMKG_API_URL    = "https://data.bmkg.go.id/DataMKG/TEWS/gempadirasakan.json"
SHAKEMAP_URL    = "https://static.bmkg.go.id/{wib_ts}.mmi.jpg"
GCS_BASE_URL    = "https://bmkg-content-inatews.storage.googleapis.com/{wib_ts}_rev/{filename}"

WIB = timezone(timedelta(hours=7))

# Bounding box for all Papua provinces (Papua, Papua Barat, Papua Tengah, etc.)
PAPUA_LON_MIN = 130.0
PAPUA_LON_MAX = 141.0
PAPUA_LAT_MIN =  -9.0
PAPUA_LAT_MAX =   2.0


def is_papua(lat, lon):
    return PAPUA_LAT_MIN <= lat <= PAPUA_LAT_MAX and PAPUA_LON_MIN <= lon <= PAPUA_LON_MAX


def wib_timestamp(dt_utc):
    """Convert UTC datetime to WIB (UTC+7) and return yyyymmddHHMMSS string."""
    dt_wib = dt_utc.astimezone(WIB)
    return dt_wib.strftime("%Y%m%d%H%M%S")


def fetch_shakemap_image(wib_ts):
    """Try to download the MMI shakemap image. Returns (filename, bytes) or (None, None)."""
    url = SHAKEMAP_URL.format(wib_ts=wib_ts)
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200 and resp.headers.get("Content-Type", "").startswith("image/"):
            return f"{wib_ts}.mmi.jpg", resp.content
    except Exception:
        pass
    return None, None


def fetch_gcs_image(wib_ts, filename):
    """Download an image from the BMKG GCS bucket. Returns (filename, bytes) or (None, None)."""
    url = GCS_BASE_URL.format(wib_ts=wib_ts, filename=filename)
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200 and resp.headers.get("Content-Type", "").startswith("image/"):
            return f"{wib_ts}_{filename}", resp.content
    except Exception:
        pass
    return None, None


class Command(BaseCommand):
    help = (
        "Fetch felt earthquakes from BMKG API, filter for Papua, download the MMI "
        "shakemap image, and save to FeltEarthquake + ShakemapEvent models."
    )

    def handle(self, *args, **options):
        self.stdout.write("Fetching BMKG felt earthquake data...")

        try:
            response = requests.get(BMKG_API_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0 (datin-fetcher)"})
            response.raise_for_status()
            events = response.json().get("Infogempa", {}).get("gempa", [])
        except Exception as e:
            self.stderr.write(f"Failed to fetch API: {e}")
            return

        self.stdout.write(f"Total events from API: {len(events)}")

        saved = skipped = 0

        for event in events:
            try:
                coords = event.get("Coordinates", "")
                lat, lon = map(float, coords.split(","))

                if not is_papua(lat, lon):
                    continue

                # Parse UTC datetime
                event_dt = datetime.fromisoformat(event["DateTime"])
                if event_dt.tzinfo is None:
                    event_dt = event_dt.replace(tzinfo=timezone.utc)

                magnitude = float(event.get("Magnitude", 0))
                depth     = float(event.get("Kedalaman", "0 km").split()[0])
                wilayah   = event.get("Wilayah", "")
                dirasakan = event.get("Dirasakan", "")

                # Build WIB timestamp for shakemap URL and event_id
                wib_ts = wib_timestamp(event_dt)

                # --- 1. Save / update FeltEarthquake ---
                felt_obj, felt_created = FeltEarthquake.objects.get_or_create(
                    event_datetime=event_dt,
                    defaults={
                        "latitude":  lat,
                        "longitude": lon,
                        "magnitude": magnitude,
                        "depth_km":  depth,
                        "wilayah":   wilayah,
                        "dirasakan": dirasakan,
                    },
                )

                # Download GCS images into FeltEarthquake if not yet saved
                gcs_fields = [
                    ("img_stationlist", "stationlist_MMI.jpg"),
                    ("img_impact_list", "impact_list.jpg"),
                    ("img_loc_map",     "loc_map.png"),
                    ("img_report_1",    "reports-1.jpg"),
                    ("img_report_2",    "reports-2.jpg"),
                ]
                gcs_updated = False
                for field_name, filename in gcs_fields:
                    if not getattr(felt_obj, field_name):
                        img_name, img_bytes = fetch_gcs_image(wib_ts, filename)
                        if img_bytes:
                            getattr(felt_obj, field_name).save(img_name, ContentFile(img_bytes), save=False)
                            gcs_updated = True
                if gcs_updated:
                    felt_obj.save()

                # --- 2. Save / update ShakemapEvent (used by existing shakemap views) ---
                shk_obj, shk_created = ShakemapEvent.objects.get_or_create(
                    event_id=wib_ts,
                    defaults={
                        "latitude":        lat,
                        "longitude":       lon,
                        "magnitude":       magnitude,
                        "depth":           depth,
                        "event_time":      event_dt,
                        "location_string": wilayah,
                    },
                )

                # --- 3. Attach shakemap image if not yet saved ---
                # Priority:
                #   a) BMKG static CDN (https://static.bmkg.go.id/<WIB>.mmi.jpg)
                #   b) Local file previously rsync'd by the .50 PUSH workflow
                #      (/var/www/html/media/shakemaps/<WIB>.mmi.jpg)
                # (b) heals the push-before-fetch race: when an operator clicks
                # PUSH on .50 before this hourly cron has created the row, the
                # image file lands on disk but no DB row exists to link it. The
                # next run of this command finds the row missing, creates it,
                # then finds the orphan file here and points the field at it.
                if not shk_obj.shakemap_image:
                    img_name, img_bytes = fetch_shakemap_image(wib_ts)
                    if img_bytes:
                        shk_obj.shakemap_image.save(img_name, ContentFile(img_bytes), save=True)
                        self.stdout.write(self.style.SUCCESS(
                            f"  SAVED  M{magnitude} {wilayah} [{event_dt:%Y-%m-%d %H:%M} UTC] + shakemap"
                        ))
                    else:
                        from django.conf import settings as _settings
                        from pathlib import Path as _Path
                        local_path = _Path(_settings.MEDIA_ROOT) / "shakemaps" / f"{wib_ts}.mmi.jpg"
                        if local_path.exists():
                            shk_obj.shakemap_image.name = str(local_path.relative_to(_settings.MEDIA_ROOT))
                            shk_obj.save(update_fields=["shakemap_image"])
                            self.stdout.write(self.style.SUCCESS(
                                f"  SAVED  M{magnitude} {wilayah} [{event_dt:%Y-%m-%d %H:%M} UTC] + shakemap (linked from .50 PUSH)"
                            ))
                        else:
                            shk_obj.save()
                            self.stdout.write(self.style.WARNING(
                                f"  SAVED  M{magnitude} {wilayah} [{event_dt:%Y-%m-%d %H:%M} UTC] (no shakemap image)"
                            ))
                    saved += 1
                else:
                    skipped += 1

            except Exception as e:
                self.stderr.write(f"  Error processing event: {e} — {event}")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Saved: {saved} new Papua events | Already existed: {skipped}"
        ))
