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


class LightningDailyGrid(models.Model):
    """Daily strike count per 0.5-degree grid cell (WIT date)."""
    grid_date = models.DateField(db_index=True, help_text="Date in WIT")
    latitude = models.FloatField(help_text="Grid cell center latitude")
    longitude = models.FloatField(help_text="Grid cell center longitude")
    cg_plus = models.IntegerField(default=0, help_text="CG+ strike count")
    cg_minus = models.IntegerField(default=0, help_text="CG- strike count")
    total = models.IntegerField(default=0, help_text="Total strike count")

    class Meta:
        unique_together = ('grid_date', 'latitude', 'longitude')
        ordering = ['grid_date', 'latitude', 'longitude']
        verbose_name = 'Daily Lightning Grid'
        verbose_name_plural = 'Daily Lightning Grids'

    def __str__(self):
        return f"{self.grid_date} ({self.latitude:.2f}, {self.longitude:.2f}) CG+={self.cg_plus} CG-={self.cg_minus}"


class LightningMonthlyGrid(models.Model):
    """Monthly aggregated strike counts + IDW-smoothed density."""
    year = models.IntegerField(db_index=True, help_text="Year")
    month = models.IntegerField(db_index=True, help_text="Month (1-12)")
    latitude = models.FloatField(help_text="Grid cell center latitude")
    longitude = models.FloatField(help_text="Grid cell center longitude")
    cg_plus = models.IntegerField(default=0, help_text="CG+ strike count (monthly)")
    cg_minus = models.IntegerField(default=0, help_text="CG- strike count (monthly)")
    total = models.IntegerField(default=0, help_text="Total strike count (monthly)")
    idw_smooth = models.FloatField(null=True, blank=True, help_text="IDW-smoothed density for color gradient")

    class Meta:
        unique_together = ('year', 'month', 'latitude', 'longitude')
        ordering = ['-year', '-month', 'latitude', 'longitude']
        verbose_name = 'Monthly Lightning Grid'
        verbose_name_plural = 'Monthly Lightning Grids'

    def __str__(self):
        return f"{self.year}-{self.month:02d} ({self.latitude:.2f}, {self.longitude:.2f}) total={self.total}"