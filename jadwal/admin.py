from django.contrib import admin
from .models import Pegawai, PolaDinas, JadwalHarian

@admin.register(Pegawai)
class PegawaiAdmin(admin.ModelAdmin):
    list_display = ('nama', 'nip', 'is_reguler', 'urutan')
    list_editable = ('urutan', 'is_reguler')

@admin.register(PolaDinas)
class PolaDinasAdmin(admin.ModelAdmin):
    list_display = ('kode', 'nama', 'durasi', 'warna')

@admin.register(JadwalHarian)
class JadwalHarianAdmin(admin.ModelAdmin):
    list_display = ('tanggal', 'pegawai', 'pola', 'keterangan_lain')
    list_filter = ('tanggal', 'pegawai', 'pola')
    date_hierarchy = 'tanggal'
    # Fitur ini memudahkan input massal
    save_as = True