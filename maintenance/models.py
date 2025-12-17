from django.db import models
from django.contrib.auth.models import User

class Instrument(models.Model):
    JENIS_CHOICES = [
        ('SEIS', 'Seismometer'),
        ('ACC', 'Accelerograph'),
        ('MAG', 'Magnetometer'),
        ('PETIR', 'Lightning Detector'),
        ('AQ', 'Air Quality'),
        ('WRS', 'WRS New Gen'),
        ('RAIN', 'Rain Gauge'),
    ]

    STATUS_ALAT_CHOICES = [
        ('AKTIF', 'Aktif'),
        ('BERMASALAH', 'Bermasalah'),
        ('MATI', 'Mati/Rusak Total'),
        ('MAINTENANCE', 'Sedang Maintenance'),
    ]

    nama_alat = models.CharField(max_length=100)
    jenis = models.CharField(max_length=10, choices=JENIS_CHOICES)
    merk_tipe = models.CharField(max_length=100, blank=True, null=True, verbose_name="Merk / Tipe")
    lokasi = models.CharField(max_length=100, help_text="Nama Lokasi atau Desa") 
    shelter = models.CharField(max_length=100, help_text="Kode Shelter/Station")
    status = models.CharField(max_length=20, choices=STATUS_ALAT_CHOICES, default='AKTIF')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.nama_alat} ({self.shelter})"
    
    class Meta:
        ordering = ['shelter', 'jenis']

class Issue(models.Model):
    KATEGORI_CHOICES = [
        ('POWER', 'Power/Listrik'),
        ('SENSOR', 'Sensor Error'),
        ('KOM', 'Komunikasi/Sinyal'),
        ('LING', 'Lingkungan (Suhu/Vandal/Banjir)'),
        ('LAIN', 'Lain-lain'),
    ]

    PRIORITAS_CHOICES = [
        ('TINGGI', 'Tinggi (Segera)'),
        ('SEDANG', 'Sedang'),
        ('RENDAH', 'Rendah'),
    ]

    STATUS_ISSUE_CHOICES = [
        ('OPEN', 'Open (Baru)'),
        ('PROG', 'In Progress'),
        ('DONE', 'Selesai'),
    ]

    instrument = models.ForeignKey(Instrument, on_delete=models.CASCADE, related_name='issues')
    judul = models.CharField(max_length=200, verbose_name="Judul Masalah")
    kategori = models.CharField(max_length=10, choices=KATEGORI_CHOICES)
    deskripsi = models.TextField()
    prioritas = models.CharField(max_length=10, choices=PRIORITAS_CHOICES, default='SEDANG')
    status = models.CharField(max_length=10, choices=STATUS_ISSUE_CHOICES, default='OPEN')
    tanggal_lapor = models.DateTimeField(auto_now_add=True)
    pic = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_issues', verbose_name="PIC / Teknisi")

    def __str__(self):
        return f"[{self.status}] {self.instrument.shelter} - {self.judul}"

class ActionLog(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name='logs')
    tanggal = models.DateTimeField(auto_now_add=True)
    tindakan = models.TextField(help_text="Detail tindakan perbaikan yang dilakukan")
    oleh = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"Log: {self.tindakan[:30]}..."