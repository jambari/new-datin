import requests
from django.core.management.base import BaseCommand
from repository.models import Gempa
from datetime import datetime
import pytz

class Command(BaseCommand):
    help = 'Import new earthquake data from the Angkasa JSON API, skipping duplicates and handling errors.'

    def handle(self, *args, **options):
        api_url = "http://36.91.166.188/api/data/balaigempas"
        self.stdout.write(f"Fetching data from API: {api_url}...")

        try:
            response = requests.get(api_url, timeout=120) # Timeout lebih panjang untuk request besar
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            self.stderr.write(self.style.ERROR(f"Failed to fetch data: {e}"))
            return

        features = data.get('features', [])
        if not features:
            self.stdout.write(self.style.WARNING("No 'features' found in the JSON response."))
            return

        created_count = 0
        skipped_count = 0
        error_count = 0
        
        # Ambil semua source_id yang sudah ada di database sekali saja untuk efisiensi
        existing_ids = set(Gempa.objects.values_list('source_id', flat=True))
        self.stdout.write(f"Found {len(existing_ids)} existing records in the database.")

        for feature in features:
            try:
                properties = feature.get('properties', {})
                geometry = feature.get('geometry', {})

                # Pastikan data esensial ada
                if not all([properties, geometry, properties.get('id'), properties.get('time')]):
                    self.stderr.write(self.style.ERROR(f"Skipping record due to missing essential data: {feature}"))
                    error_count += 1
                    continue

                source_id = f"PGR-V_{properties['id']}"

                # Cek duplikasi dengan set yang sudah diambil
                if source_id in existing_ids:
                    skipped_count += 1
                    continue
                
                # Konversi waktu dengan timezone aware
                try:
                    # Coba beberapa format tanggal yang umum
                    dt_object_utc = None
                    time_str = properties['time']
                    formats_to_try = [
                        '%Y-%m-%dT%H:%M:%S.%f%z',
                        '%Y-%m-%dT%H:%M:%S%z'
                    ]
                    for fmt in formats_to_try:
                        try:
                            dt_object_utc = datetime.strptime(time_str, fmt)
                            break
                        except ValueError:
                            continue
                    
                    if not dt_object_utc:
                        raise ValueError(f"Time data '{time_str}' does not match any known format.")

                except (ValueError, TypeError) as e:
                    self.stderr.write(self.style.ERROR(f"Skipping record ID {source_id} due to invalid date format: {e}"))
                    error_count += 1
                    continue

                # Ambil koordinat
                coords = geometry.get('coordinates')
                if not coords or len(coords) < 2:
                    self.stderr.write(self.style.ERROR(f"Skipping record ID {source_id} due to invalid coordinates."))
                    error_count += 1
                    continue
                
                longitude = coords[0]
                latitude = coords[1]
                
                # Buat objek Gempa
                Gempa.objects.create(
                    source_id=source_id,
                    station_code='PGRV', 
                    origin_datetime=dt_object_utc,
                    latitude=latitude,
                    longitude=longitude,
                    depth=properties.get('depth'),
                    magnitudo=properties.get('mag'),
                    remark=properties.get('place'),
                    felt=False, # Asumsi default
                    impact=properties.get('impact')
                )
                created_count += 1
                existing_ids.add(source_id) # Tambahkan id baru ke set agar tidak duplikat di iterasi selanjutnya

            except Exception as e:
                self.stderr.write(self.style.ERROR(f"An unexpected error occurred for feature: {feature}. Error: {e}"))
                error_count += 1
                continue

        self.stdout.write(self.style.SUCCESS(f"Import complete."))
        self.stdout.write(f"  - {created_count} new records created.")
        self.stdout.write(f"  - {skipped_count} records skipped (already exist).")
        self.stdout.write(f"  - {error_count} records failed due to data errors.")
