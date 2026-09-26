"""
scrape_gempa_merusak_images — Attach event photos to the Gempa Merusak catalog.

Searches image search engines for each event (Google Images first, then Bing
Images as fallback — Google currently serves a JavaScript-only shell to
non-browser clients and yields no results) and downloads at least --min-images
images per event into GempaMemusakMedia.

Typical usage:
    # Daily: top-up the last 5 catalog events
    python manage.py scrape_gempa_merusak_images --last 5

    # Backfill every event that still has fewer than 10 images
    python manage.py scrape_gempa_merusak_images --all --limit 50

    # Preview without downloading
    python manage.py scrape_gempa_merusak_images --last 5 --dry-run
"""
import html
import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from repository.models import GempaMemusak, GempaMemusakMedia

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')

GOOGLE_URL = 'https://www.google.com/search'
BING_URL = 'https://www.bing.com/images/search'

# Magic bytes for common image formats
_JPEG = b'\xff\xd8\xff'
_PNG = b'\x89PNG\r\n\x1a\n'
_GIF = (b'GIF87a', b'GIF89b')
_WEBP = b'RIFF'


def _http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def google_images(query, limit=20):
    """Return original image URLs from Google Images (often empty — JS wall)."""
    q = urllib.parse.quote(query)
    url = f'{GOOGLE_URL}?q={q}&udm=2&hl=en&gl=id'
    try:
        raw = _http_get(url, timeout=15).decode('utf-8', 'ignore')
    except Exception:
        return []
    urls = re.findall(r'"ou":"(https?://[^"]+)"', raw)
    seen, out = set(), []
    for u in urls:
        u = u.replace('\\u003d', '=').replace('\\u0026', '&')
        if u not in seen:
            seen.add(u)
            out.append(u)
        if len(out) >= limit:
            break
    return out


def bing_images(query, limit=20):
    """Return original image URLs (murl) from Bing Images."""
    q = urllib.parse.quote(query)
    url = f'{BING_URL}?q={q}&first=1&count=35&form=HDRSC2'
    try:
        raw = _http_get(url, timeout=15).decode('utf-8', 'ignore')
    except Exception:
        return []
    out, seen = [], set()
    for m in re.finditer(r'm="({[^"]+})"', raw):
        try:
            data = json.loads(html.unescape(m.group(1)))
        except (json.JSONDecodeError, ValueError):
            continue
        for key in ('murl', 'turl'):
            u = data.get(key)
            if u and u.startswith('http') and u not in seen:
                seen.add(u)
                out.append(u)
                break
        if len(out) >= limit:
            break
    return out


def commons_images(query, limit=20):
    """Return (url, caption) tuples from Wikimedia Commons — reliable fallback."""
    q = urllib.parse.quote(query)
    url = ('https://commons.wikimedia.org/w/api.php?action=query'
           f'&generator=search&gsrsearch={q}%20filetype:bitmap&gsrnamespace=6'
           f'&gsrlimit={limit}&prop=imageinfo&iiprop=url&iiurlwidth=800&format=json')
    try:
        raw = _http_get(url, timeout=20)
        data = json.loads(raw.decode('utf-8'))
    except Exception:
        return []
    out, seen = [], set()
    pages = data.get('query', {}).get('pages', {})
    for page in pages.values():
        info = (page.get('imageinfo') or [{}])[0]
        u = info.get('thumburl') or info.get('url')
        if not u or u in seen:
            continue
        title = (page.get('title') or '').replace('File:', '', 1).strip()
        seen.add(u)
        out.append((u, title or query))
        if len(out) >= limit:
            break
    return out


def search_images(query, needed):
    """Try Google, then Bing, then Wikimedia Commons.

    Returns a list of (url, caption) tuples.
    """
    results = []
    seen = set()

    for u in google_images(query, needed):
        if u not in seen:
            seen.add(u)
            results.append((u, query))
    if len(results) >= needed:
        return results[:needed]

    for u in bing_images(query, needed * 2):
        if u not in seen:
            seen.add(u)
            results.append((u, query))
        if len(results) >= needed:
            return results[:needed]

    for u, cap in commons_images(query, needed):
        if u not in seen:
            seen.add(u)
            results.append((u, cap))
        if len(results) >= needed:
            break
    return results[:needed]


def build_query(event):
    """Build an image-search query: prefer Indonesian place names and year."""
    place = (event.wilayah or '').strip()
    # USGS-style descriptions (e.g. "43 km ESE of Palu, Indonesia") search badly;
    # fall back to province for those.
    if not place or re.search(r'\b\d+\s*km\b|\bof\b|\b(ESE|WNW|NNE|SSW|NNW|SSE|WSW|ENE)\b',
                              place, re.IGNORECASE):
        place = (event.provinsi or '').strip() or place
    if not place:
        place = 'Indonesia'

    year = ''
    if event.tanggal:
        year = str(event.tanggal.year)
    else:
        m = re.search(r'(18|19|20)\d{2}', event.tanggal_text or '')
        if m:
            year = m.group(0)

    q = f'gempa bumi {place}'
    if year:
        q += f' {year}'
    return q.strip()


def detect_image_ext(data):
    if data[:3] == _JPEG:
        return '.jpg'
    if data[:8] == _PNG:
        return '.png'
    if data[:6] in _GIF:
        return '.gif'
    if data[:4] == _WEBP and data[8:12] == b'WEBP':
        return '.webp'
    return None


def download_one(args):
    url, caption, event_pk, idx = args
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': UA,
            'Referer': 'https://www.bing.com/',
        })
        with urllib.request.urlopen(req, timeout=20) as r:
            ctype = (r.headers.get('Content-Type') or '')
            if not ctype.startswith('image/'):
                return None
            data = r.read(4 * 1024 * 1024)  # max 4 MB
        ext = detect_image_ext(data)
        if not ext:
            return None
        event = GempaMemusak.objects.get(pk=event_pk)
        m = GempaMemusakMedia(
            event=event,
            media_type=GempaMemusakMedia.TYPE_IMAGE,
            caption=caption[:255],
        )
        name = f'gempa_merusak/evt{event_pk}_{idx}{ext}'
        m.file.save(name, ContentFile(data), save=True)
        return url
    except Exception:
        return None


class Command(BaseCommand):
    help = 'Scrape and attach event images to the Gempa Merusak catalog'

    def add_arguments(self, parser):
        parser.add_argument('--last', type=int, default=5,
                            help='Process the N newest catalog events (default 5)')
        parser.add_argument('--all', action='store_true',
                            help='Process every event that still needs images (backfill)')
        parser.add_argument('--min-images', type=int, default=10,
                            help='Minimum images per event (default 10)')
        parser.add_argument('--limit', type=int, default=None,
                            help='Max events to process in this run')
        parser.add_argument('--concurrency', type=int, default=3,
                            help='Concurrent downloads per event (default 3)')
        parser.add_argument('--delay', type=float, default=0.3,
                            help='Delay between search requests in seconds (default 0.3)')
        parser.add_argument('--dry-run', action='store_true',
                            help='Resolve queries/URLs without downloading')

    def handle(self, *args, **options):
        min_images = options['min_images']
        concurrency = options['concurrency']
        delay = options['delay']
        dry_run = options['dry_run']

        if options['all']:
            events = list(GempaMemusak.objects.order_by('-no'))
            self.stdout.write(f'Backfill mode: {len(events)} total events in catalog.')
        else:
            events = list(GempaMemusak.objects.order_by('-no')[:options['last']])
            self.stdout.write(f'Recent mode: newest {len(events)} events.')

        limit = options['limit']
        if limit is not None:
            events = events[:limit]

        processed = skipped = failed = 0
        added_total = 0

        for event in events:
            existing = event.media.count()
            needed = min_images - existing
            if needed <= 0:
                skipped += 1
                continue

            query = build_query(event)
            self.stdout.write(f'\n[{event.no}] {event.tanggal_text} | {event.wilayah or event.provinsi} '
                              f'| media {existing}/{min_images} | query: {query[:70]}')

            if dry_run:
                results = search_images(query, 5)
                self.stdout.write(f'  dry-run: found {len(results)} candidate URL(s)')
                for u, cap in results[:3]:
                    self.stdout.write(f'    {cap[:40]} | {u[:90]}')
                processed += 1
                continue

            candidates = search_images(query, needed)
            if not candidates:
                self.stdout.write(self.style.WARNING('  no image results'))
                failed += 1
                processed += 1
                continue

            self.stdout.write(f'  downloading {len(candidates)} image(s)…')
            args_list = [(u, cap, event.pk, existing + i + 1)
                         for i, (u, cap) in enumerate(candidates)]
            ok = 0
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = [pool.submit(download_one, a) for a in args_list]
                for fut in as_completed(futures):
                    if fut.result():
                        ok += 1
            added_total += ok
            processed += 1
            self.stdout.write(self.style.SUCCESS(f'  saved {ok} image(s) → total {event.media.count()}'))
            time.sleep(delay)

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. processed={processed} skipped={skipped} no_results={failed} '
            f'images_added={added_total}'
        ))
