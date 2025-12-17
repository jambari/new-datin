# repository/management/commands/backfill_shakemaps.py
import os
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from repository.models import ShakemapEvent, StationReading

# --- CONFIGURATION ---
SOURCE_DIR = '/home/sysop/new-datin/shake/'
ARCHIVE_DIR = '/home/sysop/new-datin/archive_shakemaps_backfill/'

class Command(BaseCommand):
    help = 'Backfills historical shakemap data from a source directory.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting historical shakemap backfill..."))
        os.makedirs(ARCHIVE_DIR, exist_ok=True)

        if not os.path.isdir(SOURCE_DIR):
            self.stderr.write(self.style.ERROR(f"Source directory not found: {SOURCE_DIR}"))
            return

        # --- LINES TO ADD BACK ---
        # This section finds all the subdirectories to process.
        event_folders = [f for f in os.listdir(SOURCE_DIR) if os.path.isdir(os.path.join(SOURCE_DIR, f))]
        total_folders = len(event_folders)
        self.stdout.write(f"Found {total_folders} event folders to process.")
        # --- END OF LINES TO ADD BACK ---

        for i, folder_name in enumerate(event_folders):
            self.stdout.write(f"\n--- Processing folder {i+1}/{total_folders}: {folder_name} ---")
            event_folder_path = os.path.join(SOURCE_DIR, folder_name)
            
            xml_path = os.path.join(event_folder_path, 'download', 'stationlist.xml')
            image_path = os.path.join(event_folder_path, 'download', 'intensity.jpg')

            if not os.path.exists(xml_path) or not os.path.exists(image_path):
                self.stdout.write(self.style.WARNING("stationlist.xml or intensity.jpg not found in download/ subdirectory. Skipping."))
                continue

            try:
                self.process_event_folder(xml_path, image_path)
                shutil.move(event_folder_path, os.path.join(ARCHIVE_DIR, folder_name))
                self.stdout.write(self.style.SUCCESS(f"Successfully processed and archived {folder_name}."))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"An error occurred while processing {folder_name}: {e}"))

        self.stdout.write(self.style.SUCCESS("\nHistorical backfill complete!"))

    def process_event_folder(self, xml_path, image_path):
        tree = ET.parse(xml_path)
        root = tree.getroot()

        eq_elem = root.find('earthquake')
        event_time_utc = datetime(
            int(eq_elem.get('year')), int(eq_elem.get('month')), int(eq_elem.get('day')),
            int(eq_elem.get('hour')), int(eq_elem.get('minute')), int(eq_elem.get('second')),
            tzinfo=timezone.utc
        )

        event, created = ShakemapEvent.objects.update_or_create(
            event_id=eq_elem.get('id'),
            defaults={ 'latitude': float(eq_elem.get('lat')), 'longitude': float(eq_elem.get('lon')),
                       'magnitude': float(eq_elem.get('mag')), 'depth': float(eq_elem.get('depth')),
                       'location_string': eq_elem.get('locstring'), 'event_time': event_time_utc, }
        )
        if created:
             self.stdout.write(f"Created new event: {event.event_id}")
        else:
             self.stdout.write(f"Updated existing event: {event.event_id}")

        with open(image_path, 'rb') as f:
            event.shakemap_image.save(os.path.basename(image_path), ContentFile(f.read()), save=True)

        station_list = root.find('stationlist')
        for station_elem in station_list.findall('station'):
            pga_values = {}
            for comp_elem in station_elem.findall('comp'):
                comp_name = comp_elem.get('name')
                acc_elem = comp_elem.find('acc')
                if acc_elem is not None:
                    acc_value = float(acc_elem.get('value'))
                    if 'HNE' in comp_name: pga_values['pga_ew'] = acc_value
                    elif 'HNN' in comp_name: pga_values['pga_ns'] = acc_value
                    elif 'HNZ' in comp_name: pga_values['pga_ud'] = acc_value
            
            StationReading.objects.update_or_create(
                event=event, station_code=station_elem.get('code'),
                defaults={ 'latitude': float(station_elem.get('lat')), 'longitude': float(station_elem.get('lon')),
                           'distance_km': float(station_elem.get('dist')), 'intensity': float(station_elem.get('intensity')),
                           **pga_values }
            )