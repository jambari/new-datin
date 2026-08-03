from django.db import models


class Pengaduan(models.Model):
    STATUS_CHOICES = [
        ('baru', 'Baru'),
        ('diproses', 'Diproses'),
        ('selesai', 'Selesai'),
    ]

    tanggal = models.DateField()
    nama_pelapor = models.CharField(max_length=255)
    alamat = models.TextField()
    no_hp = models.CharField(max_length=50)
    email = models.EmailField(blank=True, null=True)
    nama_terlapor = models.CharField(max_length=255)
    jabatan = models.CharField(max_length=255)
    materi_pengaduan = models.CharField(max_length=255)
    isi_pengaduan = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='baru')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'pengaduan'
        ordering = ['-created_at']
        verbose_name = 'Pengaduan'
        verbose_name_plural = 'Pengaduan'

    def __str__(self):
        return f"{self.nama_pelapor} — {self.materi_pengaduan}"
