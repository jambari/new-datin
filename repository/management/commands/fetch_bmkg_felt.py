import requests
from datetime import datetime, timezone, timedelta
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from repository.models import FeltEarthquake, ShakemapEvent

BMKG_API_URL    = "https://data.bmkg.go.id/DataMKG/TEWS/gempadirasakan.json"
# New BMKG CDN (Cloudflare) path for shakemap intensity image
SHAKEMAP_URL    = "https://www.bmkg.go.id/cdn-cgi/image/w=360,h=510/https://static.bmkg.go.id/{wib_ts}_rev/intensity_logo.jpg"
# Fallback: old direct URL (some events may not have the _rev/intensity_logo format yet)
SHAKEMAP_FALLBACK_URL = "https://static.bmkg.go.id/{wib_ts}.mmi.jpg"
GCS_BASE_URL    = "https://bmkg-content-inatews.storage.googleapis.com/{wib_ts}_rev/{filename}"

# Browser headers - required by BMKG CDN (Cloudflare) to avoid 403
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bmkg.go.id/",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}

WIB = timezone(timedelta(hours=7))

# Papua region: the six Papua provinces plus roughly 50 km of surrounding sea, as (lon, lat).
# Replaces the old 130-141E / 9S-2N box, which took in Maluku (Kep. Tanimbar, Laut Banda)
# and stopped exactly at the PNG border.
PAPUA_POLYGON = [
    (129.0, 0.5), (131.5, 1.2), (134.5, 1.3), (136.5, -0.2), (139.5, -0.6), (141.0, -1.5),
    (141.0, -9.4), (138.0, -9.0), (137.0, -7.5), (135.0, -5.0), (133.5, -4.65), (131.6, -3.3),
    (129.6, -2.4), (129.0, -1.5),
]

# Places in Papua as BMKG writes them in "Dirasakan" (kabupaten/kota and common towns)
PAPUA_PLACES = [
    "jayapura", "sentani", "abepura", "keerom", "arso", "waris", "sarmi", "mamberamo", "kasonaweja",
    "biak", "supiori", "yapen", "serui", "waropen", "botawa", "nabire", "paniai", "enarotali", "deiyai",
    "waghete", "dogiyai", "moanemani", "intan jaya", "sugapa", "puncak", "ilaga", "mulia", "mimika",
    "timika", "jayawijaya", "wamena", "lanny jaya", "tiom", "tolikara", "karubaga", "yalimo", "elelim",
    "yahukimo", "dekai", "nduga", "kenyam", "pegunungan bintang", "oksibil", "boven digoel",
    "tanah merah", "mindiptana", "merauke", "mappi", "kepi", "asmat", "agats", "manokwari", "bintuni",
    "wondama", "wasior", "fakfak", "kaimana", "arfak", "anggi", "ransiki", "sorong", "raja ampat",
    "waisai", "tambrauw", "maybrat", "kumurkek", "teminabuan", "sorong selatan", "aimas",
]


def _inside(lon, lat, ring):
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def is_papua(lat, lon):
    return _inside(lon, lat, PAPUA_POLYGON)


def felt_mostly_in_papua(dirasakan):
    """True when the first place in BMKG's "Dirasakan" list (the strongest shaking,
    e.g. "III Boven Digoel, II Jayapura, II Merauke") is in Papua."""
    first = (dirasakan or "").split(",")[0].lower()
    return any(place in first for place in PAPUA_PLACES)


# Western Papua New Guinea next to the border (Sandaun / Western Province, ~220 km wide).
# Earthquakes there from M5 upward are usually felt in Jayapura, Keerom, Boven Digoel or Merauke,
# even when BMKG's "Dirasakan" lists no Papua town.
PNG_BORDER_POLYGON = [(141.0, -1.5), (143.0, -1.5), (143.0, -9.6), (141.0, -9.6)]
PNG_MIN_MAGNITUDE = 5.0


def is_papua_event(lat, lon, dirasakan, magnitude=0.0):
    """Epicentre in the Papua region; or outside it but felt most strongly in Papua;
    or an M5+ earthquake in western PNG close to the border."""
    return (is_papua(lat, lon) or felt_mostly_in_papua(dirasakan)
            or (magnitude >= PNG_MIN_MAGNITUDE and _inside(lon, lat, PNG_BORDER_POLYGON)))


def wib_timestamp(dt_utc):
    """Convert UTC datetime to WIB (UTC+7) and return yyyymmddHHMMSS string."""
    dt_wib = dt_utc.astimezone(WIB)
    return dt_wib.strftime("%Y%m%d%H%M%S")


def fetch_shakemap_image(wib_ts):
    """Try to download the MMI shakemap / intensity image.
    Tries the new CDN URL first, then falls back to the old direct URL.
    Returns (filename, bytes) or (None, None)."""
    # Priority: 1) new BMKG CDN, 2) old static URL, 3) GCS bucket
    urls = [
        SHAKEMAP_URL.format(wib_ts=wib_ts),
        SHAKEMAP_FALLBACK_URL.format(wib_ts=wib_ts),
        f"https://bmkg-content-inatews.storage.googleapis.com/{wib_ts}_rev/intensity_logo.jpg",
    ]
    for url in urls:
        try:
            resp = requests.get(url, timeout=15, headers=_HEADERS)
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

                if not is_papua_event(lat, lon, event.get("Dirasakan", ""), float(event.get("Magnitude", 0))):
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

                # --- 1. Save / update FeltEarthquake (dedup by time ±5s + location) ---
                from django.db.models import Q
                from datetime import timedelta as _td
                felt_obj = FeltEarthquake.objects.filter(
                    event_datetime__gte=event_dt - _td(seconds=120),
                    event_datetime__lte=event_dt + _td(seconds=120),
                    latitude__gte=lat - 0.5, latitude__lte=lat + 0.5,
                    longitude__gte=lon - 0.5, longitude__lte=lon + 0.5,
                ).first()
                if felt_obj:
                    felt_created = False
                    # Update fields (magnitude may have changed)
                    felt_obj.magnitude = magnitude
                    felt_obj.depth_km = depth
                    felt_obj.wilayah = wilayah
                    felt_obj.dirasakan = dirasakan
                    felt_obj.save(update_fields=['magnitude','depth_km','wilayah','dirasakan'])
                else:
                    felt_created = True
                    felt_obj = FeltEarthquake.objects.create(
                        event_datetime=event_dt,
                        latitude=lat,
                        longitude=lon,
                        magnitude=magnitude,
                        depth_km=depth,
                        wilayah=wilayah,
                        dirasakan=dirasakan,
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
                shk_obj, shk_created = ShakemapEvent.objects.update_or_create(
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
