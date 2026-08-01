from django.db import models


class Guest(models.Model):
    nama = models.CharField(max_length=255)
    dari = models.CharField(max_length=255)
    keperluan = models.CharField(max_length=255)
    keterangan = models.TextField(blank=True, null=True)
    foto = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'guests'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.nama} - {self.dari}"
