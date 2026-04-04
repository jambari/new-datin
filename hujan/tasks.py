import json
from datetime import datetime, timedelta
import urllib.request
import logging
from celery import shared_task
from django.utils import timezone
from django.conf import settings
from hujan.models import Hujan

logger = logging.getLogger(__name__)

@shared_task
def import_today_hujan_data():
    """
    Fetches today's rain data from WIT API and saves it to the database.
    
    TIMEZONE CONTEXT:
    - API is in WIT (UTC+9)
    - Django server is in UTC
    - Users input data at 08:30 WIT = 23:30 UTC (previous day)
    - Task scheduled to run at 00:15 UTC = 09:15 WIT (buffer after user input)
    
    Returns:
        dict: Status with count of imported records
    """
    url = getattr(settings, 'HUJAN_API_URL', 'http://36.91.166.188/api/hujans/today')
    
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            raw_data = response.read()
            data = json.loads(raw_data.decode('utf-8'))
        logger.info(f"Successfully fetched data from {url}")
    except urllib.error.URLError as e:
        logger.error(f"Network error fetching data from API: {e}")
        return {'status': 'error', 'message': f'Network error: {e}', 'imported': 0}
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error from API: {e}")
        return {'status': 'error', 'message': f'Invalid JSON response: {e}', 'imported': 0}
    except Exception as e:
        logger.error(f"Unexpected error fetching data from API: {e}")
        return {'status': 'error', 'message': str(e), 'imported': 0}

    if 'data' not in data or not isinstance(data['data'], list):
        logger.warning("Invalid data format. 'data' key not found or is not a list.")
        return {'status': 'error', 'message': 'Invalid data format', 'imported': 0}

    new_entries = []
    skipped = 0
    errors = 0
    
    for item in data['data']:
        try:
            tanggal = datetime.strptime(item['tanggal'], '%Y-%m-%d').date()
            obs = float(item['obs'])

            # Check for existing entry to prevent duplicates based on tanggal and obs
            # Use exists() for efficiency instead of filtering then checking
            if Hujan.objects.filter(tanggal=tanggal, obs=obs).exists():
                skipped += 1
                continue

            new_entries.append(Hujan(
                tanggal=tanggal,
                hilman=float(item.get('hilman', 0)),
                obs=obs,
                kategori=item.get('kategori', ''),
                keterangan=item.get('keterangan'),
                petugas=item.get('petugas') or 'staff ops'
            ))
        except (ValueError, KeyError, TypeError) as e:
            logger.warning(f"Skipping malformed entry: {e}. Data: {item}")
            errors += 1
            continue

    if new_entries:
        Hujan.objects.bulk_create(new_entries)
        logger.info(f"✅ Successfully imported {len(new_entries)} new rain records. "
                   f"(Skipped: {skipped} duplicates, {errors} errors)")
        return {'status': 'success', 'imported': len(new_entries), 'skipped': skipped, 'errors': errors}
    else:
        logger.info(f"No new rain records to import. (Skipped: {skipped} duplicates, {errors} errors)")
        return {'status': 'success', 'imported': 0, 'skipped': skipped, 'errors': errors}


@shared_task
def import_hujan_data_retry():
    """
    Retry task for importing rain data.
    Runs 2 hours after the main import to catch any delayed data updates.
    
    Useful as a safety net in case API was slow or data was delayed.
    """
    logger.info("Running retry import for hujan data...")
    return import_today_hujan_data()