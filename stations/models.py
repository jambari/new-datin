from django.db import models


class Station(models.Model):
    network = models.CharField(max_length=10)
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=100, blank=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    elevation = models.FloatField(default=0)
    channel = models.CharField(max_length=10, default='HNN')
    sensor = models.CharField(max_length=50, blank=True)
    digitizer = models.CharField(max_length=50, blank=True)
    kota = models.CharField(max_length=50, blank=True)
    provinsi = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('network', 'code')
        ordering = ['code']

    def __str__(self):
        return f"{self.network}.{self.code}"


class StationStatus(models.Model):
    STATUS_CHOICES = [('on', 'ON'), ('gap', 'GAP'), ('off', 'OFF')]
    station = models.OneToOneField(Station, on_delete=models.CASCADE, related_name='status')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='off')
    latency = models.FloatField(null=True, blank=True)
    last_packet_time = models.DateTimeField(null=True, blank=True)
    last_updated = models.DateTimeField(auto_now=True)
    channel_info = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return f"{self.station.code} — {self.status}"

    @staticmethod
    def compute_status(latency_seconds):
        if latency_seconds is None:
            return 'off'
        if 0.02 <= latency_seconds <= 1800:
            return 'on'
        if 1800 < latency_seconds <= 3600:
            return 'gap'
        return 'off'
