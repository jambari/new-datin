from django.contrib import admin
from .models import Pegawai, JenisPerjadin, PerjalananDinas

@admin.register(JenisPerjadin)
class JenisPerjadinAdmin(admin.ModelAdmin):
    list_display = ('nama', 'tarif_harian')
    search_fields = ('nama',)

@admin.register(PerjalananDinas)
class PerjalananDinasAdmin(admin.ModelAdmin):
    list_display = ('pegawai', 'tujuan', 'jenis', 'tgl_mulai', 'tgl_selesai')
    list_filter = ('jenis', 'tgl_mulai')
    search_fields = ('pegawai__nama', 'tujuan')