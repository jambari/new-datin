from django.db import models


class Layanan(models.Model):
    nama = models.CharField(max_length=255, blank=True, null=True)
    instansi = models.CharField(max_length=255, blank=True, null=True)
    alamat = models.CharField(max_length=255, blank=True, null=True)
    email = models.CharField(max_length=255, blank=True, null=True)
    handphone = models.CharField(max_length=255, blank=True, null=True)
    jenis_data = models.CharField(max_length=255, blank=True, null=True)
    surat = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'layanans'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.nama} - {self.jenis_data}"
