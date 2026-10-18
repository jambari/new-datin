import json
from django.core.management.base import BaseCommand
import urllib.request
from hujan.categories import normalize_kategori
from hujan.models import Hujan
from datetime import datetime

class Command(BaseCommand):
    help = 'Imports rain data from the specified API endpoint.'

    def handle(self, *args, **options):
        url = 'http://36.91.166.188/api/data/hujans'
        self.stdout.write(self.style.NOTICE(f"Starting rain data import from {url}..."))

        try:
            with urllib.request.urlopen(url) as response:
                raw_data = response.read()
                data = json.loads(raw_data.decode('utf-8'))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error fetching/parsing JSON: {e}"))
            return

        if 'data' not in data or not isinstance(data['data'], list):
            self.stderr.write(self.style.ERROR("Invalid data format. 'data' key not found or is not a list."))
            return

        total_imported = 0
        new_entries = []

        for item in data['data']:
            try:
                tanggal = datetime.strptime(item['tanggal'], '%Y-%m-%d').date()
                obs = float(item['obs'])

                if not Hujan.objects.filter(tanggal=tanggal, obs=obs).exists():
                    new_entries.append(Hujan(
                        tanggal=tanggal,
                        hilman=float(item.get('hilman', 0)),
                        obs=obs,
                        kategori=normalize_kategori(item.get('kategori')) or item.get('kategori') or '',
                        keterangan=item.get('keterangan'),
                        petugas=item.get('petugas') or 'staff ops' # Handle null explicitly
                    ))
            except Exception as e:
                self.stderr.write(self.style.WARNING(f"Skipping malformed entry: {e}. Data: {item}"))
                continue
                
        if new_entries:
            Hujan.objects.bulk_create(new_entries)
            total_imported = len(new_entries)
            self.stdout.write(self.style.SUCCESS(f"✅ Successfully imported {total_imported} new rain records."))
        else:
            self.stdout.write(self.style.NOTICE("No new rain records to import."))
        
        self.stdout.write(self.style.SUCCESS("🎉 Import process finished."))