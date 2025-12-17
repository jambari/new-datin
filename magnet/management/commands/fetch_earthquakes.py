import requests
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.gis.geos import Point
from magnet.models import Earthquake

# Alamat API yang Anda berikan
API_URL = "http://36.91.166.188/api/data/balaigempas"
MIN_MAGNITUDE = 5.0

class Command(BaseCommand):
    help = f'Mengambil data gempa (M > {MIN_MAGNITUDE}) dari API dan menyimpannya ke database.'

    def handle(self, *args, **options):
        self.stdout.write("Memulai pengambilan data gempa dari API...")
        
        try:
            response = requests.get(API_URL, timeout=20)
            response.raise_for_status()  # Cek jika ada error HTTP
            earthquake_data = response.json()
        except requests.RequestException as e:
            self.stderr.write(self.style.ERROR(f"Gagal mengambil data dari API: {e}"))
            return

        new_earthquakes_count = 0
        for eq_data in earthquake_data:
            magnitude = float(eq_data.get('magnitudo', 0))
            event_id = eq_data.get('event_id')

            # Lewati jika magnitudo < 5.0 atau tidak ada event_id
            if magnitude <= MIN_MAGNITUDE or not event_id:
                continue

            # Cek duplikasi berdasarkan event_id
            if Earthquake.objects.filter(event_id=event_id).exists():
                continue

            try:
                # Konversi waktu dari string. Asumsikan waktu dari API adalah UTC.
                # Jika bukan, perlu penyesuaian timezone.
                event_time_str = eq_data['waktu_kejadian']
                event_time_naive = datetime.strptime(event_time_str, '%Y-%m-%d %H:%M:%S')
                event_time_aware = timezone.make_aware(event_time_naive, timezone.utc)

                # Buat objek Point untuk GeoDjango
                latitude = float(eq_data['lintang'])
                longitude = float(eq_data['bujur'])
                
                Earthquake.objects.create(
                    event_id=event_id,
                    event_time=event_time_aware,
                    location_point=Point(longitude, latitude, srid=4326),
                    depth=float(eq_data.get('kedalaman', 0)),
                    magnitude=magnitude,
                    region=eq_data.get('wilayah', 'Tidak diketahui')
                )
                new_earthquakes_count += 1
            except (ValueError, KeyError) as e:
                self.stderr.write(self.style.WARNING(f"Gagal memproses data gempa ID {event_id}: {e}"))

        self.stdout.write(self.style.SUCCESS(
            f"Proses selesai. Berhasil menyimpan {new_earthquakes_count} data gempa baru."
        ))
