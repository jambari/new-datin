from django.db import models

# Create your models here.
class Hujan(models.Model):
    tanggal = models.DateField()
    hilman = models.FloatField(default=0)
    obs = models.FloatField()
    kategori = models.CharField(max_length=50)
    keterangan = models.CharField(max_length=255, blank=True, null=True)
    petugas = models.CharField(max_length=50, default="staff ops") # Set default value

    class Meta:
        db_table = 'hujan'
        verbose_name_plural = "hujan"
        ordering = ['-tanggal']
    
    def __str__(self):
        return f"Hujan pada {self.tanggal} ({self.obs}mm)"