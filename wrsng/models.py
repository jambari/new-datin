from django.db import models
from django.utils import timezone # Import timezone
import datetime

class WRSNGStatus(models.Model):
    """
    Menyimpan log histori status dari WRSNG Display.
    Setiap entri adalah satu kejadian/laporan status.
    """
    
    # --- Pilihan Status ---
    STATUS_ON = 1
    STATUS_OFF = 0

    STATUS_CHOICES = [
        (STATUS_ON, 'OK / Online'),
        (STATUS_OFF, 'Off / Mati'),
    ]

    # --- Fields ---
    
    # DIUBAH: dari DateField menjadi DateTimeField
    # Menggunakan 'default=timezone.now' berarti jika WRSNG mengirim data
    # tanpa timestamp, server akan menggunakan waktunya saat ini.
    status_datetime = models.DateTimeField(default=timezone.now, db_index=True, help_text="Waktu pasti status ini dilaporkan")
    
    # Kode unik untuk setiap WRS Display
    wrs_code = models.CharField(max_length=100, db_index=True)
    
    # Koordinat (opsional, bisa null)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    
    # Status display
    display_status = models.IntegerField(
        choices=STATUS_CHOICES, 
        default=STATUS_ON,
        help_text="Status monitor display (misal: menyala, mati, error)"
    )
    
    # Status aplikasi
    chrome_status = models.IntegerField(
        choices=STATUS_CHOICES, 
        default=STATUS_ON,
        help_text="Status aplikasi (misal: Chrome berjalan, error)"
    )
    
    # Catatan tambahan
    remark = models.TextField(blank=True, null=True)
    
    # DIHAPUS: last_updated tidak lagi diperlukan karena status_datetime
    # sudah mencatat waktu kejadian.

    class Meta:
        # DIHAPUS: unique_together dihapus agar bisa menyimpan banyak status per hari.
        # unique_together = ('date', 'wrs_code') 
        
        # DIUBAH: Mengurutkan berdasarkan waktu status yang baru
        ordering = ['-status_datetime', 'wrs_code'] 
        verbose_name = "WRSNG Status Log"
        verbose_name_plural = "WRSNG Status Logs"

    def __str__(self):
        # DIUBAH: Menampilkan timestamp lengkap
        return f"{self.wrs_code} on {self.status_datetime} (Display: {self.get_display_status_display()})"
    
class WRSNGDataAvailability(models.Model):
    """
    Menyimpan persentase availability harian WRSNG (Manual/Report).
    """
    station = models.CharField(max_length=100) # wrs_code
    date = models.DateField()
    percentage = models.FloatField(default=0.0)
    channel = models.CharField(max_length=10, default='REPORT')
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('station', 'date', 'channel')
        verbose_name = "WRSNG Data Availability"
        verbose_name_plural = "WRSNG Data Availabilities"

    def __str__(self):
        return f"{self.station} - {self.date}: {self.percentage}%"