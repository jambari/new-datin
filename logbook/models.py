from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Logbook(models.Model):
    SHIFT_CHOICES = [
        ('Pagi', 'Pagi'),
        ('Siang', 'Siang'),
        ('Malam', 'Malam'),
        ('Pagi Siang', 'Pagi Siang'),
        ('Pagi Siang Malam', 'Pagi Siang Malam'),
    ]

    STATUS_CHOICES = [
        ('ON', 'ON'),
        ('OFF', 'OFF'),
    ]

    # --- NEW: Shift Status Choices ---
    ABSEN_CHOICES = [
        ('Masuk', 'Awal Shift (Masuk)'),
        ('Pulang', 'Akhir Shift (Pulang)'),
    ]

    # Metadata
    petugas = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='logs_as_petugas')
    tanggal = models.DateField(default=timezone.now)
    waktu_dibuat = models.DateTimeField(auto_now_add=True)

    # --- NEW FIELDS ---
    status_absen = models.CharField(
        max_length=20, 
        choices=ABSEN_CHOICES, 
        default='Masuk',
        verbose_name="Status Absen"
    )

    petugas_sebelum = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='logs_as_previous',
        verbose_name="Petugas Shift Sebelumnya"
    )

    petugas_selanjutnya = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='logs_as_next',
        verbose_name="Petugas Shift Selanjutnya"
    )

    # Existing Fields
    shift = models.CharField(max_length=50, choices=SHIFT_CHOICES)
    seiscomp_seismik = models.CharField(max_length=3, choices=STATUS_CHOICES, default='OFF', verbose_name="Seiscomp Seismik")
    seiscomp_accelero = models.CharField(max_length=3, choices=STATUS_CHOICES, default='OFF', verbose_name="Seiscomp Accelero")
    esdx = models.CharField(max_length=3, choices=STATUS_CHOICES, default='OFF', verbose_name="ESDX")
    petir = models.CharField(max_length=3, choices=STATUS_CHOICES, default='OFF', verbose_name="Petir")
    lemi = models.CharField(max_length=3, choices=STATUS_CHOICES, default='OFF', verbose_name="LEMI")
    proton = models.CharField(max_length=3, choices=STATUS_CHOICES, default='OFF', verbose_name="Proton")
    catatan = models.TextField(blank=True, null=True, verbose_name="Catatan")

    class Meta:
        ordering = ['-tanggal', '-waktu_dibuat']
        verbose_name = "Logbook Harian"
        verbose_name_plural = "Logbook Harian"

    def __str__(self):
        return f"Log {self.tanggal} - {self.shift}"