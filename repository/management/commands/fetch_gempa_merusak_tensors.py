"""
fetch_gempa_merusak_tensors — Fetch USGS moment-tensor solutions for the
Gempa Merusak catalog and store nodal-plane (strike/dip/rake) parameters.

For each event that has a parsed date and coordinates, we query the USGS
FDSN event service for a moment-tensor product near the epicenter, fetch the
event detail feed, and store nodal plane 1 (strike, dip, rake) plus the
source label.

Usage:
    # Fetch tensors for all events that don't have one yet
    python manage.py fetch_gempa_merusak_tensors

    # Preview
    python manage.py fetch_gempa_merusak_tensors --dry-run --limit 20

    # Re-fetch (overwrite) everything
    python manage.py fetch_gempa_merusak_tensors --refetch
"""
import datetime
import json
import logging
import time
import urllib.parse
import urllib.request

from django.core.management.base import BaseCommand
from django.db.models import Q

from repository.models import GempaMemusak

log = logging.getLogger(__name__)

FDSN_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
DETAIL_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/detail/{eid}.geojson"
UA = "datin-bmkg/1.0 (contact: jambari@bmkg.go.id)"


def _http_json(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _distance_km(lat1, lon1, lat2, lon2):
    import math
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def find_usgs_event(event):
    """Return the nearest USGS event feature with a moment tensor, or None."""
    if not event.tanggal or event.latitude is None or event.longitude is None:
        return None
    start = datetime.datetime.combine(event.tanggal, datetime.time.min) - datetime.timedelta(hours=12)
    end = start + datetime.timedelta(days=1) + datetime.timedelta(hours=12)
    params = {
        "format": "geojson",
        "starttime": start.isoformat(),
        "endtime": end.isoformat(),
        "latitude": f"{event.latitude:.4f}",
        "longitude": f"{event.longitude:.4f}",
        "maxradiuskm": "100",
        "producttype": "moment-tensor",
    }
    url = f"{FDSN_URL}?{urllib.parse.urlencode(params)}"
    data = _http_json(url)
    features = data.get("features", [])
    if not features:
        return None
    best = min(features, key=lambda f: _distance_km(
        event.latitude, event.longitude,
        f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0]))
    return best


def get_tensor(event_id):
    """Return (strike, dip, rake, mag) from the USGS detail feed."""
    data = _http_json(DETAIL_URL.format(eid=event_id))
    products = data.get("properties", {}).get("products", {})
    mt = products.get("moment-tensor")
    if not mt:
        return None
    pr = mt[0].get("properties", {})
    try:
        strike = float(pr["nodal-plane-1-strike"])
        dip = float(pr["nodal-plane-1-dip"])
        rake = float(pr["nodal-plane-1-rake"])
    except (KeyError, TypeError, ValueError):
        return None
    mag = pr.get("derived-magnitude")
    return strike, dip, rake, mag


class Command(BaseCommand):
    help = "Fetch USGS moment-tensor solutions for the Gempa Merusak catalog"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--refetch", action="store_true",
                            help="Re-fetch events that already have a tensor")
        parser.add_argument("--delay", type=float, default=0.4)

    def handle(self, *args, **options):
        qs = GempaMemusak.objects.filter(
            tanggal__isnull=False, latitude__isnull=False, longitude__isnull=False)
        if not options["refetch"]:
            qs = qs.filter(Q(strike__isnull=True) | Q(dip__isnull=True) | Q(rake__isnull=True))
        qs = qs.order_by("-no")
        total = qs.count()
        if options["limit"]:
            qs = qs[:options["limit"]]

        self.stdout.write(f"Candidates: {total} (limit {options['limit'] or 'none'})")
        found = missing = 0

        for ev in qs:
            try:
                feat = find_usgs_event(ev)
            except Exception as exc:
                self.stdout.write(f"[{ev.no}] {ev.tanggal_text} SEARCH ERROR: {exc}")
                time.sleep(options["delay"])
                continue

            if feat is None:
                missing += 1
                self.stdout.write(f"[{ev.no}] {ev.tanggal_text} | {ev.wilayah[:30]} -> no USGS moment tensor")
            else:
                eid = feat["id"]
                try:
                    tensor = get_tensor(eid)
                except Exception as exc:
                    self.stdout.write(f"[{ev.no}] {ev.tanggal_text} DETAIL ERROR ({eid}): {exc}")
                    time.sleep(options["delay"])
                    continue
                if tensor is None:
                    missing += 1
                    self.stdout.write(f"[{ev.no}] {ev.tanggal_text} -> {eid} has no MT properties")
                else:
                    strike, dip, rake, mag = tensor
                    dist = _distance_km(ev.latitude, ev.longitude,
                                        feat["geometry"]["coordinates"][1],
                                        feat["geometry"]["coordinates"][0])
                    found += 1
                    self.stdout.write(
                        f"[{ev.no}] {ev.tanggal_text} -> {eid} "
                        f"({dist:.0f} km) S/D/R={strike:.1f}/{dip:.1f}/{rake:.1f}")
                    if not options["dry_run"]:
                        ev.strike = strike
                        ev.dip = dip
                        ev.rake = rake
                        ev.tensor_source = "USGS"
                        ev.save(update_fields=["strike", "dip", "rake", "tensor_source"])
            time.sleep(options["delay"])

        if options["dry_run"]:
            self.stdout.write("Dry run — nothing saved.")
        self.stdout.write(self.style.SUCCESS(
            f"Done. found={found} missing={missing}"))
