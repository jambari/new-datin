from datetime import date

from django.db import models


class Peralatan(models.Model):
    STATUS_CHOICES = [
        ("BMN", "BMN"),
        ("SUKU_CADANG", "Suku Cadang"),
    ]

    nama_alat = models.CharField(max_length=150)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="SUKU_CADANG",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nama_alat"]

    def __str__(self):
        return self.nama_alat


class Peminjaman(models.Model):
    STATUS_CHOICES = [
        ("BELUM_DIKEMBALIKAN", "Belum Dikembalikan"),
        ("SUDAH_DIKEMBALIKAN", "Sudah Dikembalikan"),
        ("RUSAK", "Rusak"),
        ("HILANG", "Hilang"),
    ]

    tanggal_peminjaman = models.DateField(default=date.today)
    surat_tugas = models.CharField(max_length=255)
    peralatan = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=25,
        choices=STATUS_CHOICES,
        default="BELUM_DIKEMBALIKAN",
    )
    tanggal_pengembalian = models.DateField(null=True, blank=True)
    keterangan = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.surat_tugas

    def get_peralatan_ids(self):
        if not isinstance(self.peralatan, list):
            return []
        ids = []
        for item in self.peralatan:
            try:
                ids.append(int(item))
            except (TypeError, ValueError):
                continue
        return ids

    def get_peralatan_queryset(self):
        return Peralatan.objects.filter(id__in=self.get_peralatan_ids()).order_by("nama_alat")

    def get_primary_peralatan_name(self):
        item = self.get_peralatan_queryset().first()
        return item.nama_alat if item else "-"

    def get_peralatan_names_display(self):
        names = list(self.get_peralatan_queryset().values_list("nama_alat", flat=True))
        return ", ".join(names) if names else "-"


class PeralatanSukuCadang(models.Model):
    jenis_alat = models.CharField(max_length=150, verbose_name="Jenis Alat")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["jenis_alat"]
        verbose_name = "Peralatan Suku Cadang"
        verbose_name_plural = "Peralatan Suku Cadang"

    def __str__(self):
        return self.jenis_alat


class ManajemenSukuCadang(models.Model):
    STATUS_CHOICES = [
        ("BELUM_TERPASANG", "Belum Terpasang"),
        ("SUDAH_TERPASANG", "Sudah Terpasang"),
        ("RUSAK", "Rusak"),
    ]

    tanggal_masuk = models.DateField(default=date.today, verbose_name="Tanggal Masuk")
    jenis = models.ForeignKey(
        PeralatanSukuCadang,
        on_delete=models.PROTECT,
        related_name="manajemen_items",
        verbose_name="Jenis",
    )
    merk = models.CharField(max_length=150, verbose_name="Merk")
    serial_number = models.CharField(max_length=150, verbose_name="Serial Number")
    jumlah = models.PositiveIntegerField(default=1, verbose_name="Jumlah")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="BELUM_TERPASANG",
        verbose_name="Status",
    )
    keterangan = models.TextField(blank=True, verbose_name="Keterangan")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-tanggal_masuk", "-created_at"]
        verbose_name = "Manajemen Suku Cadang"
        verbose_name_plural = "Manajemen Suku Cadang"

    def __str__(self):
        return f"{self.jenis} - {self.merk} ({self.serial_number})"
