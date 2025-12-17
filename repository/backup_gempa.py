import json
from dateutil import parser
import urllib.request
import os

from django.core.management.base import BaseCommand
from django.db.models import F
from django.conf import settings
from celery import shared_task
from repository.models import Gempa


# Define your management command as a function
def sync_earthquake_data_from_sources():
    """
    Syncs earthquake events from multiple station JSON URLs.
    This function contains the core logic of your management command.
    """
    STATION_SOURCES = {
        'JAY': 'http://36.91.166.188/api/angkasa/forshakemap',
        'PGRV': 'http://36.91.166.188/api/earthquakes',
        'NBPI': 'http://36.91.166.188/api/nabire/forshakemap',
        'SWI': 'http://36.91.166.188/api/sorong/forshakemap',
    }

    print("Starting event synchronization from multiple stations...")

    total_new_events = 0

    for station_code, json_url in STATION_SOURCES.items():
        print(f"\nFetching data for station: {station_code} ({json_url})")

        try:
            with urllib.request.urlopen(json_url) as response:
                raw_data = response.read()
                encoding = response.info().get_content_charset('utf-8')
                data = json.loads(raw_data.decode(encoding))
        except Exception as e:
            print(f"Error fetching/parsing JSON from {station_code}: {e}")
            continue

        existing_unique_ids = set(Gempa.objects.values_list('source_id', flat=True))
        new_events_to_create = []

        for feature in data.get('features', []):
            properties = feature.get('properties', {})
            raw_id = properties.get('id')

            if raw_id is None:
                continue

            unique_id = f"{int(raw_id):05d}_{station_code.upper().replace(' ', '')}"

            if unique_id in existing_unique_ids:
                continue

            try:
                geometry = feature.get('geometry', {})
                coordinates = geometry.get('coordinates', [None, None])

                latitude = float(coordinates[1])
                longitude = float(coordinates[0])
                origin_datetime = parser.parse(properties.get('time'))
                magnitude = float(properties.get('mag', 0))
                depth = int(properties.get('depth', 0))
                remark = properties.get('place', '')
                
                felt_status = bool(properties.get('felt', False))
                impact_remark = properties.get('impact', None)

                new_event = Gempa(
                    source_id=unique_id,
                    station_code=station_code.upper().replace(' ', ''),
                    origin_datetime=origin_datetime,
                    latitude=latitude,
                    longitude=longitude,
                    magnitudo=magnitude,
                    depth=depth,
                    remark=remark,
                    felt=felt_status,
                    impact=impact_remark,
                )

                new_events_to_create.append(new_event)
                existing_unique_ids.add(unique_id)

            except Exception as e:
                print(f"Skipping malformed event '{raw_id}': {e}")
                continue

        if new_events_to_create:
            Gempa.objects.bulk_create(new_events_to_create)
            print(f"✅ Added {len(new_events_to_create)} new events for station {station_code}.")
            total_new_events += len(new_events_to_create)
        else:
            print(f"No new events for station {station_code}.")

    print(f"\n🎉 Sync complete. Total new events: {total_new_events}")
    return f"Sync complete. Total new events: {total_new_events}"

# Celery task to call the sync function
@shared_task
def sync_earthquake_data_task():
    """
    Celery task that triggers the earthquake data synchronization.
    """
    sync_earthquake_data_from_sources()