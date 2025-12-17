# magnet/models.py
from django.db import models
from django.contrib.gis.db import models as gis_models
from repository.models import Gempa
from django import forms

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

    # Calculated results (we will populate these later)
    meridian_1 = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    meridian_2 = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    
    declination = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    inclination = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    horizontal_intensity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_intensity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-observation_date', '-session']

    def __str__(self):
        return f"Observation on {self.observation_date} by {self.observer} ({self.session})"
    

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
