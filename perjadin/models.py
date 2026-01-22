from django.db import models
from django.db.models import Sum

from jadwal.models import Pegawai

class JenisPerjadin(models.Model):
    nama = models.CharField(max_length=100) # Misal: Harian Luar Kota
    tarif_harian = models.DecimalField(max_digits=12, decimal_places=0)

    def __str__(self):
        return f"{self.nama} (Rp {self.tarif_harian:,.0f})"

class PerjalananDinas(models.Model):
    pegawai = models.ForeignKey(Pegawai, on_delete=models.CASCADE, related_name='perjadins')
    jenis = models.ForeignKey(JenisPerjadin, on_delete=models.PROTECT)
    tujuan = models.CharField(max_length=255)
    kegiatan = models.CharField(max_length=255, blank=True, null=True)
    tgl_mulai = models.DateField()
    tgl_selesai = models.DateField()

    @property
    def durasi_hari(self):
        return (self.tgl_selesai - self.tgl_mulai).days + 1

    @property
    def total_biaya(self):
        return self.durasi_hari * self.jenis.tarif_harian