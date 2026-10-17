"""Peta dasar statis OpenStreetMap (tile disimpan di cache lokal)."""
import math
import urllib.request
from pathlib import Path

from django.conf import settings
from PIL import Image

TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
USER_AGENT = "datin-reporting/1.0 (Stasiun Geofisika Kelas I Jayapura, BMKG)"
ATTRIBUTION = "© OpenStreetMap contributors"


def _cache_dir():
    path = Path(getattr(settings, "OSM_TILE_CACHE", Path(settings.BASE_DIR) / "cache" / "osm_tiles"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def deg2num(lat, lon, zoom):
    n = 2 ** zoom
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def _tile(z, x, y):
    path = _cache_dir() / f"{z}_{x}_{y}.png"
    if not path.exists():
        req = urllib.request.Request(TILE_URL.format(z=z, x=x, y=y), headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            path.write_bytes(resp.read())
    return Image.open(path).convert("RGB")


class StaticMap:
    """Mozaik tile OSM untuk kotak (lat0, lat1, lon0, lon1) pada zoom tertentu."""

    def __init__(self, lat0, lat1, lon0, lon1, zoom=10):
        self.zoom = zoom
        self.lat0, self.lat1, self.lon0, self.lon1 = lat0, lat1, lon0, lon1
        self.x0, self.y0 = deg2num(lat1, lon0, zoom)
        x1, y1 = deg2num(lat0, lon1, zoom)
        tx0, ty0, tx1, ty1 = int(self.x0), int(self.y0), int(x1), int(y1)
        mosaic = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256))
        for tx in range(tx0, tx1 + 1):
            for ty in range(ty0, ty1 + 1):
                mosaic.paste(_tile(zoom, tx, ty), ((tx - tx0) * 256, (ty - ty0) * 256))
        box = (int((self.x0 - tx0) * 256), int((self.y0 - ty0) * 256),
               int((x1 - tx0) * 256), int((y1 - ty0) * 256))
        self.image = mosaic.crop(box)
        self.width, self.height = self.image.size

    def project(self, lat, lon):
        x, y = deg2num(lat, lon, self.zoom)
        return (x - self.x0) * 256, (y - self.y0) * 256
