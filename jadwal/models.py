from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

class Pegawai(models.Model):
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True)
    nama = models.CharField(max_length=100)
    nip = models.CharField(max_length=30, unique=True)
    pangkat = models.CharField(max_length=100, help_text="Contoh: Penata Muda Tk.I (III/b)")
    jabatan = models.CharField(max_length=100, help_text="Contoh: PMG Pertama")
    is_reguler = models.BooleanField(default=False, help_text="Centang jika pegawai ini pola kerjanya Reguler (Senin-Jumat)")
    urutan = models.IntegerField(default=0, help_text="Untuk mengatur urutan baris di tabel")
    tanggal_keluar = models.DateField(null=True, blank=True, help_text="Isi jika pegawai pindah/pensiun. Pegawai otomatis hilang dari jadwal setelah tanggal ini.")

    def __str__(self):
        return self.nama
    
    class Meta:
        ordering = ['urutan', 'nama']

class PolaDinas(models.Model):
    kode = models.CharField(max_length=10, unique=True, help_text="Contoh: P, S, M, PSM, R")
    nama = models.CharField(max_length=50, help_text="Contoh: Pagi, Siang, Malam")
    jam_mulai = models.TimeField()
    jam_selesai = models.TimeField()
    durasi = models.FloatField(help_text="Total jam kerja (decimal). Contoh: 7.5 atau 12.5")
    warna = models.CharField(max_length=20, default="#FFFFFF", help_text="Kode warna Hex, cth: #FF0000")
    is_libur = models.BooleanField(default=False, help_text="Centang jika ini adalah kode untuk Libur/Lepas Dinas/Cuti")

    def __str__(self):
        return f"{self.kode} ({self.durasi} Jam)"

class JadwalHarian(models.Model):
    STATUS_CHOICES = [
        ('HADIR', 'Hadir'),
        ('DL', 'Dinas Luar'),
        ('CUTI', 'Cuti'),
        ('SAKIT', 'Sakit'),
        ('IZIN', 'Izin'),
        ('TB', 'Tugas Belajar'),
    ]

    pegawai = models.ForeignKey(Pegawai, on_delete=models.CASCADE, related_name='jadwal_harian')
    tanggal = models.DateField()
    pola = models.ForeignKey(PolaDinas, on_delete=models.SET_NULL, null=True, blank=True)
    keterangan_lain = models.CharField(max_length=10, choices=STATUS_CHOICES, blank=True, null=True, help_text="Isi jika status bukan dinas biasa (misal DL/Cuti)")

    class Meta:
        unique_together = ('pegawai', 'tanggal')
        verbose_name = "Input Jadwal"
        verbose_name_plural = "Input Jadwal"

    def __str__(self):
        return f"{self.pegawai} - {self.tanggal}"
    

class RiwayatJadwal(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True) # Siapa yang mengubah
    bulan = models.IntegerField()
    tahun = models.IntegerField()
    keterangan = models.CharField(max_length=150) # Contoh: "Backup sebelum Generate"
    data_snapshot = models.JSONField() # Menyimpan seluruh jadwal dalam format JSON

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.keterangan} - {self.created_at.strftime('%d/%m %H:%M')}"