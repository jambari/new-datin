from django.contrib import admin
from .models import Pegawai, PolaDinas, JadwalHarian, JadwalHVSampler

@admin.register(Pegawai)
class PegawaiAdmin(admin.ModelAdmin):
    list_display = ('nama', 'nip', 'is_reguler', 'urutan', 'tanggal_keluar')
    list_editable = ('urutan','tanggal_keluar', 'is_reguler')

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


# Tambahkan di admin.py
from .models import Pegawai, PolaDinas, JadwalHarian, JadwalHVSampler # Pastikan import diupdate

@admin.register(JadwalHVSampler)
class JadwalHVSamplerAdmin(admin.ModelAdmin):
    list_display = ('tanggal', 'tipe', 'catatan_khusus')
    list_filter = ('tipe', 'tanggal')
    date_hierarchy = 'tanggal'
    search_fields = ('catatan_khusus',)
    
    # Memudahkan input massal jika diperlukan
    save_as = True