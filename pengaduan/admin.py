from django.contrib import admin
from .models import Pengaduan


@admin.register(Pengaduan)
class PengaduanAdmin(admin.ModelAdmin):
    list_display = ('tanggal', 'nama_pelapor', 'materi_pengaduan', 'nama_terlapor', 'status', 'created_at')
    list_filter = ('status', 'tanggal', 'materi_pengaduan')
    search_fields = ('nama_pelapor', 'nama_terlapor', 'materi_pengaduan', 'isi_pengaduan', 'no_hp', 'email')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    list_editable = ('status',)

    fieldsets = (
        ('Data Pelapor', {
            'fields': ('tanggal', 'nama_pelapor', 'alamat', 'no_hp', 'email')
        }),
        ('Data Terlapor', {
            'fields': ('nama_terlapor', 'jabatan')
        }),
        ('Isi Pengaduan', {
            'fields': ('materi_pengaduan', 'isi_pengaduan')
        }),
        ('Status', {
            'fields': ('status', 'created_at', 'updated_at')
        }),
    )
