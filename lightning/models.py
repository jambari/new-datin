# lightning/models.py
from django.db import models

# lightning/models.py
from django.db import models

class Strike(models.Model):
    # Hapus unique=True dari epoch_ms
    epoch_ms = models.BigIntegerField(db_index=True) # Hapus unique=True
    timestamp = models.DateTimeField(db_index=True)
    latitude = models.FloatField(null=True)
    longitude = models.FloatField(null=True)
    strike_type = models.IntegerField(null=True)

    class Meta:
        indexes = [
            models.Index(fields=['timestamp']),
            # Anda masih bisa index epoch_ms untuk pencarian cepat,
            # tapi tidak harus unique
            models.Index(fields=['epoch_ms']),
        ]

class DailyStrikeSummary(models.Model):
    # The date this summary represents (local time, e.g., WIT)
    summary_date = models.DateField(unique=True, db_index=True)
    # Counts for different strike types
    cg_plus_count = models.PositiveIntegerField(default=0)
    cg_minus_count = models.PositiveIntegerField(default=0)
    # Assuming Type 2 is Intracloud (IC)
    ic_count = models.PositiveIntegerField(default=0)
    # Optional: Count for other/unknown types if needed
    other_count = models.PositiveIntegerField(default=0)
    # Total count for the day
    total_count = models.PositiveIntegerField(default=0)
    # Timestamp of the last update for this date's summary
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return (f"{self.summary_date}: CG+({self.cg_plus_count}), "
                f"CG-({self.cg_minus_count}), IC({self.ic_count}), Total({self.total_count})")

    class Meta:
        verbose_name = "Daily Strike Summary"
        verbose_name_plural = "Daily Strike Summaries"
        ordering = ['-summary_date'] # Show latest summaries first by default

# --- MODEL BARU UNTUK AVAILABILITY ---
class LightningDataAvailability(models.Model):
    """
    Menyimpan persentase availability harian stasiun Lightning Detector.
    """
    station = models.CharField(max_length=20) # Misal: 'JAY LD', 'BIK LD'
    date = models.DateField()
    percentage = models.FloatField(default=0.0)
    # Field 'channel' disimpan untuk kompatibilitas struktur, default REPORT
    channel = models.CharField(max_length=10, default='REPORT') 
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('station', 'date', 'channel')
        verbose_name = "Lightning Availability"
        verbose_name_plural = "Lightning Availabilities"

    def __str__(self):
        return f"{self.station} - {self.date}: {self.percentage}%"