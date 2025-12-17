import json
from datetime import datetime
import urllib.request
from celery import shared_task
from hujan.models import Hujan

@shared_task
def import_today_hujan_data():
    """
    Fetches today's rain data from an API and saves it to the database.
    """
    url = 'http://36.91.166.188/api/hujans/today'
    
    try:
        with urllib.request.urlopen(url) as response:
            raw_data = response.read()
            data = json.loads(raw_data.decode('utf-8'))
    except Exception as e:
        print(f"Error fetching data from API: {e}")
        return

    if 'data' not in data or not isinstance(data['data'], list):
        print("Invalid data format. 'data' key not found or is not a list.")
        return

    new_entries = []
    
    for item in data['data']:
        try:
            tanggal = datetime.strptime(item['tanggal'], '%Y-%m-%d').date()
            obs = float(item['obs'])

            # Check for existing entry to prevent duplicates based on tanggal and obs
            if not Hujan.objects.filter(tanggal=tanggal, obs=obs).exists():
                new_entries.append(Hujan(
                    tanggal=tanggal,
                    hilman=float(item.get('hilman', 0)),
                    obs=obs,
                    kategori=item.get('kategori', ''),
                    keterangan=item.get('keterangan'),
                    petugas=item.get('petugas') or 'staff ops'
                ))
        except Exception as e:
            print(f"Skipping malformed entry: {e}. Data: {item}")
            continue

    if new_entries:
        Hujan.objects.bulk_create(new_entries)
        print(f"✅ Successfully imported {len(new_entries)} new rain records.")
    else:
        print("No new rain records to import.")