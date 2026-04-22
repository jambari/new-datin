# repository/models.py
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User

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
    shakemap_image = models.ImageField(upload_to='shakemaps/', null=True, blank=True)

    def __str__(self):
        return f"{self.event_id} - M{self.magnitude} at {self.location_string}"


class FeltEarthquake(models.Model):
    """Gempabumi dirasakan di wilayah Papua, diambil dari API BMKG."""
    event_datetime  = models.DateTimeField(unique=True, db_index=True)
    latitude        = models.FloatField()
    longitude       = models.FloatField()
    magnitude       = models.FloatField()
    depth_km        = models.FloatField()
    wilayah         = models.CharField(max_length=300)
    dirasakan       = models.CharField(max_length=500, blank=True)
    fetched_at      = models.DateTimeField(auto_now_add=True)
    img_stationlist = models.ImageField(upload_to='felt_earthquakes/stationlist/', null=True, blank=True)
    img_impact_list = models.ImageField(upload_to='felt_earthquakes/impact/', null=True, blank=True)
    img_loc_map     = models.ImageField(upload_to='felt_earthquakes/locmap/', null=True, blank=True)
    img_report_1    = models.ImageField(upload_to='felt_earthquakes/reports/', null=True, blank=True)
    img_report_2    = models.ImageField(upload_to='felt_earthquakes/reports/', null=True, blank=True)

    class Meta:
        ordering = ['-event_datetime']

    def __str__(self):
        return f"M{self.magnitude} {self.wilayah} ({self.event_datetime:%Y-%m-%d %H:%M} UTC)"


class JSONDataUpload(models.Model):
    """
    Model untuk menyimpan file JSON yang di-upload oleh user
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    file_name = models.CharField(max_length=255)
    agency = models.CharField(max_length=50, blank=True, null=True)
    region = models.CharField(max_length=100, blank=True, null=True)
    bulan = models.CharField(max_length=10, blank=True, null=True)  # YYYYMM format
    json_file = models.FileField(upload_to='json_uploads/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    data_count = models.IntegerField(default=0)  # Jumlah event dalam JSON
    
    class Meta:
        db_table = 'json_data_uploads'
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.file_name} - {self.uploaded_at.strftime('%Y-%m-%d')}"