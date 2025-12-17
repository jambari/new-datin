import json
from django.core.management.base import BaseCommand
from repository.models import Gempa
from datetime import datetime

class Command(BaseCommand):
    help = 'Import new earthquake data from a local JSON file, skipping duplicates and handling errors.'

    def add_arguments(self, parser):
        # Menambahkan argumen untuk path file JSON
        parser.add_argument('json_file_path', type=str, help='The full path to the balaigempas.json file.')

    def handle(self, *args, **options):
        file_path = options['json_file_path']
        self.stdout.write(f"Reading data from local file: {file_path}...")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f"Error: The file was not found at '{file_path}'"))
            return
        except json.JSONDecodeError:
            self.stderr.write(self.style.ERROR(f"Error: The file at '{file_path}' is not a valid JSON file."))
            return
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"An unexpected error occurred while reading the file: {e}"))
            return

        features = data.get('features', [])
        if not features:
            self.stdout.write(self.style.WARNING("No 'features' found in the JSON file."))
            return

        created_count = 0
        skipped_count = 0
        error_count = 0
        
        existing_ids = set(Gempa.objects.values_list('source_id', flat=True))
        self.stdout.write(f"Found {len(existing_ids)} existing records in the database.")

        for feature in features:
            try:
                properties = feature.get('properties', {})
                geometry = feature.get('geometry', {})

                if not all([properties, geometry, properties.get('id'), properties.get('time')]):
                    self.stderr.write(self.style.ERROR(f"Skipping record due to missing essential data: {feature}"))
                    error_count += 1
                    continue

                source_id = f"PGR-V_{properties['id']}"

                if source_id in existing_ids:
                    skipped_count += 1
                    continue
                
                try:
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

                coords = geometry.get('coordinates')
                if not coords or len(coords) < 2:
                    self.stderr.write(self.style.ERROR(f"Skipping record ID {source_id} due to invalid coordinates."))
                    error_count += 1
                    continue
                
                longitude = coords[0]
                latitude = coords[1]
                
                Gempa.objects.create(
                    source_id=source_id,
                    station_code='PGRV', 
                    origin_datetime=dt_object_utc,
                    latitude=latitude,
                    longitude=longitude,
                    depth=properties.get('depth'),
                    magnitudo=properties.get('mag'),
                    remark=properties.get('place'),
                    felt=False,
                    impact=properties.get('impact')
                )
                created_count += 1
                existing_ids.add(source_id)

            except Exception as e:
                self.stderr.write(self.style.ERROR(f"An unexpected error occurred for feature: {feature}. Error: {e}"))
                error_count += 1
                continue

        self.stdout.write(self.style.SUCCESS(f"Import complete."))
        self.stdout.write(f"  - {created_count} new records created.")
        self.stdout.write(f"  - {skipped_count} records skipped (already exist).")
        self.stdout.write(f"  - {error_count} records failed due to data errors.")

