# repository/models.py
from django.db import models
from django.utils import timezone

class Gempa(models.Model):
    source_id = models.CharField(max_length=50, unique=True, null=True, blank=True, help_text="ID gabungan dari sumber API dan kode stasiun")
    station_code = models.CharField(max_length=10, db_index=True)
    
    # --- Ganti 'tanggal' dan 'origin_time' dengan baris ini ---
    origin_datetime = models.DateTimeField(help_text="Waktu kejadian gempa dalam UTC")
    
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    magnitudo = models.DecimalField(max_digits=3, decimal_places=1)
    depth = models.IntegerField()
    remark = models.CharField(max_length=191)
    felt = models.BooleanField(default=False)
    impact = models.CharField(max_length=191, blank=True, null=True)

    class Meta:
        db_table = 'gempas'
        ordering = ['-origin_datetime'] # Urutkan berdasarkan field baru

    def __str__(self):
        return f"Gempa on {self.origin_datetime} - M{self.magnitudo}"
    

class Station(models.Model):
    code = models.CharField(max_length=10, unique=True)
    network = models.CharField(max_length=10)
    name = models.CharField(max_length=100, null=True, blank=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    elevation = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    

    def __str__(self):
        return f"{self.code} ({self.network})"
    
class DataAvailability(models.Model):
    station = models.CharField(max_length=10, db_index=True)
    channel = models.CharField(max_length=10)
    date = models.DateField(db_index=True)
    percentage = models.FloatField()
    reported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Mencegah entri duplikat untuk stasiun, channel, dan tanggal yang sama
        unique_together = ['station', 'channel', 'date']
        ordering = ['-date', 'station', 'channel']

    def __str__(self):
        return f"{self.station} - {self.channel} on {self.date}: {self.percentage}%"
    

class AcceleroDataAvailability(models.Model):
    station = models.CharField(max_length=10, db_index=True, help_text="Station code (e.g., JAY)")
    channel = models.CharField(max_length=10, db_index=True, help_text="Channel code (e.g., EHZ)")
    date = models.DateField(help_text="Date of the data availability record")
    percentage = models.FloatField(help_text="Percentage of data available for the day (0-100)")
    reported_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        # Prevents duplicate entries for the same station, channel, and date
        unique_together = ('station', 'channel', 'date')
        db_table = 'accelero_data_availability'
        verbose_name_plural = 'Accelero Data Availability'
        ordering = ['-date', 'station', 'channel']

    def __str__(self):
        return f"{self.station} - {self.channel} on {self.date}: {self.percentage:.2f}%"
    
class ShakemapEvent(models.Model):
    event_id = models.CharField(max_length=100, unique=True, db_index=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    magnitude = models.FloatField()
    depth = models.FloatField()
    event_time = models.DateTimeField(default=timezone.now)
    location_string = models.CharField(max_length=255)
    shakemap_image = models.ImageField(upload_to='shakemaps/')

    def __str__(self):
        return f"{self.event_id} - M{self.magnitude} at {self.location_string}"

class StationReading(models.Model):
    # Updated the ForeignKey to point to the new model name
    event = models.ForeignKey(ShakemapEvent, related_name='stations', on_delete=models.CASCADE)
    station_code = models.CharField(max_length=10, db_index=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    distance_km = models.FloatField()
    intensity = models.FloatField(help_text="Instrumental Intensity")
    pga_ew = models.FloatField(null=True, blank=True, help_text="East-West component")
    pga_ns = models.FloatField(null=True, blank=True, help_text="North-South component")
    pga_ud = models.FloatField(null=True, blank=True, help_text="Up-Down (Vertical) component")

    class Meta:
        unique_together = ('event', 'station_code')

    def __str__(self):
        return f"{self.station_code} for event {self.event.event_id}"