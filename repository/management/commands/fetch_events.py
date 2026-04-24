"""
Fetch earthquake events from the QuakeLink browser at
http://172.19.2.185:18080/events/browse/{year}/{month}/{day}
and store them in the EventBrowser model.

Usage:
  python manage.py fetch_events              # Jan 1 2025 → today, skip already-fetched days
  python manage.py fetch_events --today      # today only (re-fetch)
  python manage.py fetch_events --from 2025-03-01   # re-fetch from a specific date
"""

import math
import re
import datetime
import time

import requests
from lxml import html as lhtml
from django.core.management.base import BaseCommand
from django.utils import timezone

from repository.models import EventBrowser, ReferenceLocation

BASE_URL = 'http://172.19.2.185:18080/events/browse'
START_DATE = datetime.date(2025, 1, 1)


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def nearest_city(lat, lon, cities):
    best_name, best_dist = '', float('inf')
    for c in cities:
        d = haversine(lat, lon, c.latitude, c.longitude)
        if d < best_dist:
            best_dist = d
            best_name = c.name
    return best_name, round(best_dist, 1)


def fetch_day(date):
    url = f"{BASE_URL}/{date.year}/{date.month}/{date.day}"
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return r.text
    except Exception as e:
        return None


def parse_html(content):
    """Return list of dicts with raw event data."""
    tree = lhtml.fromstring(content.encode('utf-8'))
    rows = tree.xpath('//table[@id="list"]/tbody/tr')
    events = []
    for row in rows:
        onclick = row.get('onclick', '')
        m = re.search(r"/events/browse/rev/([^'\"]+)", onclick)
        if not m:
            continue
        event_id = m.group(1).strip()

        cells = row.xpath('td')
        if len(cells) < 14:
            continue

        origin_time_str = (cells[1].text_content() or '').strip()
        mag_title       = (cells[2].get('title') or '').strip()
        lat_title       = (cells[3].get('title') or '').strip()
        lon_title       = (cells[4].get('title') or '').strip()
        depth_title     = (cells[5].get('title') or '').strip()
        location        = (cells[13].text_content() or '').strip()

        try:
            origin_time = datetime.datetime.strptime(origin_time_str, '%Y-%m-%d %H:%M:%S')
            origin_time = origin_time.replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue

        try:
            magnitude = float(mag_title.split()[0])
        except (ValueError, IndexError):
            continue

        try:
            latitude = float(lat_title)
        except ValueError:
            continue

        try:
            longitude = float(lon_title)
        except ValueError:
            continue

        try:
            depth_km = float(depth_title)
        except ValueError:
            depth_km = 0.0

        events.append({
            'event_id':    event_id,
            'origin_time': origin_time,
            'magnitude':   magnitude,
            'latitude':    latitude,
            'longitude':   longitude,
            'depth_km':    depth_km,
            'location':    location,
        })
    return events


class Command(BaseCommand):
    help = 'Fetch events from QuakeLink and store in EventBrowser'

    def add_arguments(self, parser):
        parser.add_argument('--today', action='store_true', help='Only fetch today')
        parser.add_argument('--from', dest='from_date', type=str, help='Re-fetch from this date (YYYY-MM-DD)')

    def handle(self, *args, **options):
        today = datetime.date.today()
        cities = list(ReferenceLocation.objects.all())

        if options['today']:
            dates = [today]
        elif options['from_date']:
            try:
                start = datetime.date.fromisoformat(options['from_date'])
            except ValueError:
                self.stderr.write('Invalid date format. Use YYYY-MM-DD.')
                return
            dates = [start + datetime.timedelta(days=i) for i in range((today - start).days + 1)]
        else:
            dates = [START_DATE + datetime.timedelta(days=i) for i in range((today - START_DATE).days + 1)]

        total_new = total_updated = total_days = 0

        for date in dates:
            # Skip past days already imported (but always re-fetch today)
            if date < today and not options['from_date']:
                if EventBrowser.objects.filter(origin_time__date=date).exists():
                    continue

            html = fetch_day(date)
            if html is None:
                self.stderr.write(f'  Failed to fetch {date}')
                continue

            events = parse_html(html)
            if not events:
                self.stdout.write(f'  {date}: 0 events')
                total_days += 1
                continue

            day_new = day_updated = 0
            for ev in events:
                city_name, dist = nearest_city(ev['latitude'], ev['longitude'], cities)
                obj, created = EventBrowser.objects.update_or_create(
                    event_id=ev['event_id'],
                    defaults={
                        'origin_time':  ev['origin_time'],
                        'magnitude':    ev['magnitude'],
                        'latitude':     ev['latitude'],
                        'longitude':    ev['longitude'],
                        'depth_km':     ev['depth_km'],
                        'location':     ev['location'],
                        'nearest_city': city_name,
                        'distance_km':  dist,
                    }
                )
                if created:
                    day_new += 1
                else:
                    day_updated += 1

            total_new     += day_new
            total_updated += day_updated
            total_days    += 1
            self.stdout.write(f'  {date}: {len(events)} events ({day_new} new, {day_updated} updated)')
            time.sleep(0.1)  # be polite to the server

        self.stdout.write(self.style.SUCCESS(
            f'Done — {total_days} days processed, {total_new} new, {total_updated} updated'
        ))
