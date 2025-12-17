import requests
from datetime import datetime
from django.core.management.base import BaseCommand
from repository.models import Gempa

class Command(BaseCommand):
    help = 'Import new earthquake data from the Angkasa JSON API, avoiding duplicates.'

    def handle(self, *args, **kwargs):
        api_url = "http://36.91.166.188/api/data/yesterday/soronggempas"
        
        self.stdout.write(f"Fetching data from {api_url}...")
        
        try:
            response = requests.get(api_url, timeout=120)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            self.stdout.write(self.style.ERROR(f"Failed to fetch data: {e}"))
            return

        # Ambil semua ID sumber yang sudah ada di database untuk pemeriksaan duplikat
        station_code = 'SWI' # Definisikan kode stasiun Anda di sini
        existing_ids = set(Gempa.objects.values_list('source_id', flat=True))
        self.stdout.write(f"Found {len(existing_ids)} existing records in the database.")

        gempas_to_create = []
        for feature in data.get('features', []):
            properties = feature.get('properties', {})

            id_from_json = properties.get('id')
            if not id_from_json:
                continue

            source_id = f"{id_from_json:02d}{station_code}"
            # Lewati jika ID gabungan sudah ada
            if source_id in existing_ids:
                continue

            # ... (sisa logika parsing Anda tetap sama) ...
            try:
                geometry = feature.get('geometry', {})
                time_str = properties.get('time')
                dt_object = datetime.fromisoformat(time_str)
                coordinates = geometry.get('coordinates')
                
                gempa_instance = Gempa(
                    source_id=source_id,
                    station_code=station_code,
                    origin_datetime=dt_object,
                    latitude=coordinates[1],          # Diperbarui
                    longitude=coordinates[0],         # Diperbarui
                    magnitudo=properties.get('mag'),
                    depth=properties.get('depth'),
                    remark=properties.get('place'),   # Diperbarui
                    felt=properties.get('felt_reports', 'tidak').lower() != 'tidak', # Diperbarui
                    impact=properties.get('impact') if properties.get('impact') != 'n' else None, # Diperbarui
                )
                gempas_to_create.append(gempa_instance)
                existing_ids.add(source_id)

            except (TypeError, KeyError, IndexError, ValueError) as e:
                self.stdout.write(self.style.WARNING(f"Skipping feature due to parsing error: {e}"))

        if gempas_to_create:
            Gempa.objects.bulk_create(gempas_to_create)
            self.stdout.write(self.style.SUCCESS(f'Successfully imported {len(gempas_to_create)} new records.'))
        else:
            self.stdout.write(self.style.SUCCESS('No new records to import.'))