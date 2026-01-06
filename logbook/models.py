from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Logbook(models.Model):
    SHIFT_CHOICES = [
        ('Pagi', 'Pagi'),
        ('Siang', 'Siang'),
        ('Malam', 'Malam'),
        ('Pagi Siang', 'Pagi Siang'),
        ('Malam Tengah Malam', 'Malam Tengah Malam'),
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

    petugas_sebelum = models.ManyToManyField(
        User, 
        blank=True, 
        related_name='logs_as_previous',
        verbose_name="Petugas Shift Sebelumnya"
    )

    petugas_selanjutnya = models.ManyToManyField(
            User, 
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
    hv_counter_hour = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Counter Hour")
    hv_flow_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Flow Rate")
    hv_berat_kertas = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, verbose_name="Berat Kertas (gr)")
    hv_jam_pasang = models.TimeField(null=True, blank=True, verbose_name="Jam Pemasangan HV")
    hv_jam_angkat = models.TimeField(null=True, blank=True, verbose_name="Jam Pengangkatan HV")
    catatan = models.TextField(blank=True, null=True, verbose_name="Catatan")

    class Meta:
        ordering = ['-tanggal', '-waktu_dibuat']
        verbose_name = "Logbook Harian"
        verbose_name_plural = "Logbook Harian"

    def __str__(self):
        return f"Log {self.tanggal} - {self.shift}"



