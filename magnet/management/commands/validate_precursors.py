from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point # Diperlukan untuk membuat objek Point
from magnet.models import Precursor
from repository.models import Gempa # Import model Gempa

class Command(BaseCommand):
    help = 'Memvalidasi prekursor dengan data dari tabel `gempas` yang sudah ada.'

    def handle(self, *args, **options):
        unvalidated_precursors = Precursor.objects.filter(
            is_validated=False, 
            location_polygon__isnull=False
        )
        
        self.stdout.write(f"Menemukan {unvalidated_precursors.count()} prekursor untuk divalidasi...")
        validated_count = 0

        for precursor in unvalidated_precursors:
            min_mag = precursor.predicted_magnitude - precursor.magnitude_tolerance
            max_mag = precursor.predicted_magnitude + precursor.magnitude_tolerance
            
            # 1. Filter Gempa berdasarkan rentang waktu dan magnitudo terlebih dahulu
            potential_gempas = Gempa.objects.filter(
                origin_datetime__date__gte=precursor.predicted_start_date,
                origin_datetime__date__lte=precursor.predicted_end_date,
                magnitude__gte=min_mag,
                magnitude__lte=max_mag,
            )
            
            matching_gempa = None
            # 2. Lakukan iterasi untuk mengecek lokasi secara manual
            for gempa in potential_gempas:
                if gempa.longitude is None or gempa.latitude is None:
                    continue
                
                # Buat objek Point dari data longitude dan latitude
                gempa_point = Point(float(gempa.longitude), float(gempa.latitude), srid=4326)
                
                # Cek apakah titik gempa berada di dalam poligon prekursor
                if gempa_point.within(precursor.location_polygon):
                    matching_gempa = gempa
                    break # Hentikan jika sudah menemukan gempa pertama yang cocok

            if matching_gempa:
                precursor.is_validated = True
                precursor.validating_earthquake = matching_gempa
                precursor.save()
                validated_count += 1
                self.stdout.write(self.style.SUCCESS(
                    f"  -> Prekursor ID {precursor.id} TERBUKTI oleh gempa: {matching_gempa}"
                ))
        
        self.stdout.write(self.style.SUCCESS(
            f"Validasi selesai. {validated_count} prekursor berhasil divalidasi."
        ))