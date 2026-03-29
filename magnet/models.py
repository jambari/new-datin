# magnet/models.py
from django.db import models
from django.contrib.gis.db import models as gis_models
from repository.models import Gempa
from django import forms
import math
from decimal import Decimal

class MagneticObservation(models.Model):
    # Main observation details
    observation_date = models.DateField()
    observer = models.CharField(max_length=100)
    session = models.CharField(max_length=50)

    # Titik tetap readings
    cr_awal = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    cl_awal = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    cr_akhir = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    cl_akhir = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)

    # Reading data stored as JSON
    deklinasi_readings = models.JSONField(null=True, blank=True)
    inklinasi_readings = models.JSONField(null=True, blank=True)

    # Calculated results (Meridian)
    meridian_1 = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    meridian_2 = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    
    # Komponen Utama
    declination = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    inclination = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    total_intensity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Komponen Turunan
    horizontal_intensity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    vertical_intensity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    north_component = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    east_component = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-observation_date', '-session']

    def __str__(self):
        return f"Observation on {self.observation_date} by {self.observer} ({self.session})"

    @property
    def is_bartington(self):
        if self.deklinasi_readings:
            for key, val in self.deklinasi_readings.items():
                if not key.startswith('_'):
                    return 'deg' in val
        return False

    def save(self, *args, **kwargs):
        """
        Kalkulasi otomatis Reduksi Theodolite & Komponen Magnetik (Standar SOP BMKG).
        """
        # Helper function untuk mengubah dict JSON (deg, min, sec) ke desimal
        def get_dec(data_dict):
            if not data_dict:
                return Decimal('0')

            def safe(val):
                try:
                    return float(str(val).strip())
                except:
                    return 0.0

            if 'deg' in data_dict:
                d = safe(data_dict.get('deg'))
                m = safe(data_dict.get('min'))
                s = safe(data_dict.get('sec'))
                result = d + (m / 60.0) + (s / 3600.0)
                return Decimal(str(result))

            elif 'circ' in data_dict:
                result = safe(data_dict.get('circ')) * 0.9
                return Decimal(str(result))

            return Decimal('0')

        if self.is_bartington and self.deklinasi_readings and self.inklinasi_readings:
            # ==========================================================
            # 1. DEKLINASI (D) - SOP BMKG
            # Berdasarkan SOP, D = Rata-rata (WU, ED, WD, EU) - 180 derajat
            # ==========================================================
            wu = get_dec(self.deklinasi_readings.get('WU'))
            ed = get_dec(self.deklinasi_readings.get('ED'))
            wd = get_dec(self.deklinasi_readings.get('WD'))
            eu = get_dec(self.deklinasi_readings.get('EU'))

            avg_dek = (wu + ed + wd + eu) / Decimal('4')
            d_val = avg_dek - Decimal('180')
            self.declination = Decimal(str(round(d_val, 5)))

            # ==========================================================
            # 2. INKLINASI (I) - SOP BMKG (Hemisfer Selatan = Negatif)
            # ==========================================================
            nu = get_dec(self.inklinasi_readings.get('NU'))
            sd = get_dec(self.inklinasi_readings.get('SD'))
            nd = get_dec(self.inklinasi_readings.get('ND'))
            su = get_dec(self.inklinasi_readings.get('SU'))

            i_nu = Decimal('180') - nu
            i_sd = Decimal('360') - sd
            i_nd = nd - Decimal('180')
            i_su = su

            i_val = -((i_nu + i_sd + i_nd + i_su) / Decimal('4'))
            self.inclination = Decimal(str(round(i_val, 5)))

            # ==========================================================
            # 3. TOTAL INTENSITY (F) RATA-RATA
            # ==========================================================
            f_totals = []
            for reading_key in ['NU', 'SD', 'ND', 'SU']:
                f_val = self.inklinasi_readings.get(reading_key, {}).get('ftotal')
                if f_val:
                    try: f_totals.append(float(f_val))
                    except ValueError: pass
            
            if len(f_totals) == 4:
                f_avg = Decimal(str(sum(f_totals))) / Decimal('4')
                self.total_intensity = Decimal(str(round(f_avg, 2)))

        # ==========================================================
        # 4. HITUNG KOMPONEN TURUNAN (H, Z, X, Y)
        # ==========================================================
        if self.total_intensity and self.declination is not None and self.inclination is not None:
            f = float(self.total_intensity)
            
            d_rad = math.radians(float(self.declination))
            i_rad = math.radians(float(self.inclination))

            h = f * math.cos(i_rad)
            z = f * math.sin(i_rad)
            x = h * math.cos(d_rad)
            y = h * math.sin(d_rad)

            self.horizontal_intensity = round(h, 2)
            self.vertical_intensity = round(z, 2)
            self.north_component = round(x, 2)
            self.east_component = round(y, 2)

        super().save(*args, **kwargs)
    

class Precursor(models.Model):
    """
    Model untuk menyimpan data prekursor atau prediksi gempa bumi.
    """
    # ... (Field lain seperti anomaly_timestamp, predicted_magnitude, dll tetap sama) ...
    anomaly_timestamp = models.DateTimeField(
        verbose_name="Waktu Anomali",
        help_text="Waktu anomali terdeteksi"
    )
    predicted_start_date = models.DateField(
        verbose_name="Tanggal Mulai Prediksi"
    )
    predicted_end_date = models.DateField(
        verbose_name="Tanggal Akhir Prediksi"
    )
    
    predicted_magnitude = models.FloatField(
        verbose_name="Prediksi Magnitudo"
    )
    magnitude_tolerance = models.FloatField(
        default=0.5, 
        verbose_name="Toleransi Magnitudo (+/-)",
        help_text="Contoh: Jika prediksi 6.0 dan toleransi 0.5, maka rentang valid adalah 5.5 - 6.5"
    )
    location_description = models.CharField(
        max_length=255, 
        verbose_name="Deskripsi Lokasi",
        help_text="Deskripsi singkat mengenai area prediksi"
    )
    
    location_polygon = gis_models.PolygonField(
        verbose_name="Area Poligon Prediksi",
        help_text="Area prediksi yang digambar di peta",
        null=True, 
        blank=True
    )

    azimuth = models.FloatField(null=True, blank=True, verbose_name="Azimuth (°)")

    is_validated = models.BooleanField(
        default=False, 
        verbose_name="Terbukti?"
    )
    
    # --- PERUBAHAN DI SINI ---
    # 2. Arahkan ForeignKey ke model Gempa dari aplikasi repository
    validating_earthquake = models.ForeignKey(
        Gempa, # <-- Menggunakan model Gempa
        on_delete=models.SET_NULL, 
        related_name="validated_precursors",
        null=True, 
        blank=True,
        verbose_name="Gempa yang Memvalidasi"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    def __str__(self):
        return f"Prekursor untuk {self.location_description} ({self.predicted_start_date} s/d {self.predicted_end_date})"
    
class MagnetDataAvailability(models.Model):
    """
    Menyimpan persentase availability harian stasiun Magnet.
    """
    station = models.CharField(max_length=20) # Misal: 'JYP_P', 'JYP_V'
    date = models.DateField()
    percentage = models.FloatField(default=0.0)
    # Field 'channel' disimpan untuk kompatibilitas struktur, default REPORT
    channel = models.CharField(max_length=10, default='REPORT') 
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('station', 'date', 'channel')
        verbose_name = "Magnet Availability"
        verbose_name_plural = "Magnet Availabilities"

    def __str__(self):
        return f"{self.station} - {self.date}: {self.percentage}%"