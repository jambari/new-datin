# monitor/models.py
from django.contrib.gis.db import models  # CHANGE THIS IMPORT

class EarthquakeEvent(models.Model):
    event_id = models.CharField(max_length=50, unique=True, primary_key=True)
    origin_time = models.DateTimeField()
    magnitude = models.FloatField()
    
    # Keep these for display
    latitude = models.FloatField()
    longitude = models.FloatField()
    
    # --- ADD THIS NEW FIELD ---
    # This is the field GeoDjango uses for spatial filtering
    location = models.PointField(srid=4326, null=True, blank=True) 
    
    depth = models.FloatField(help_text="Depth in km")
    phases = models.IntegerField(null=True, blank=True)
    agency = models.CharField(max_length=50, null=True, blank=True)
    status = models.CharField(max_length=10, null=True, blank=True)
    event_type = models.CharField(max_length=50, null=True, blank=True)
    region = models.CharField(max_length=255)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-origin_time']
        verbose_name = "Earthquake Event"

    def __str__(self):
        return f"{self.event_id} - M{self.magnitude} {self.region}"