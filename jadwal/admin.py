from django.contrib import admin
from .models import Pegawai, PolaDinas, JadwalHarian, JadwalHVSampler, Lapbul

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
    save_as = True


@admin.register(JadwalHVSampler)
class JadwalHVSamplerAdmin(admin.ModelAdmin):
    list_display = ('tanggal', 'tipe', 'catatan_khusus')
    list_filter = ('tipe', 'tanggal')
    date_hierarchy = 'tanggal'
    search_fields = ('catatan_khusus',)
    save_as = True


@admin.register(Lapbul)
class LapbulAdmin(admin.ModelAdmin):
    list_display = ('lapbul_obs', 'pic_lapbul_obs', 'lapbul_datin', 'pic_lapbul_datin', 'bulan', 'tahun', 'deadline')
    list_filter = ('tahun', 'bulan')
    search_fields = ('lapbul_obs', 'lapbul_datin', 'pic_lapbul_obs', 'pic_lapbul_datin')
