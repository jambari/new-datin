# repository/management/commands/process_shakemaps.py
import os
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from repository.models import ShakemapEvent, StationReading # <-- UPDATED: Uses your app name 'repository'

# IMPORTANT: Create these directories on your server and update the paths if needed
INCOMING_DIR = '/home/sysop/new-datin/incoming_shakemaps/'
ARCHIVE_DIR = '/home/sysop/new-datin/archive_shakemaps/'

class Command(BaseCommand):
    help = 'Processes new shakemap XML files and images from the incoming directory.'

    def handle(self, *args, **options):
        self.stdout.write("Starting shakemap processing...")
        os.makedirs(INCOMING_DIR, exist_ok=True)
        os.makedirs(ARCHIVE_DIR, exist_ok=True)

        for filename in os.listdir(INCOMING_DIR):
            if filename.endswith('.xml'):
                xml_path = os.path.join(INCOMING_DIR, filename)
                # The SCP script renames intensity.jpg to match the event_id
                image_path = os.path.join(INCOMING_DIR, os.path.splitext(filename)[0] + '.jpg')

                if not os.path.exists(image_path):
                    self.stderr.write(f"Image for {filename} not found. Skipping.")
                    continue

                self.stdout.write(f"Processing {filename}...")
                try:
                    self.process_files(xml_path, image_path)
                    # Move processed files to archive
                    shutil.move(xml_path, ARCHIVE_DIR)
                    shutil.move(image_path, ARCHIVE_DIR)
                    self.stdout.write(self.style.SUCCESS(f"Successfully processed and archived {filename}."))
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"Error processing {filename}: {e}"))

    def process_files(self, xml_path, image_path):
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