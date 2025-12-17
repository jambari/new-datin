from django.contrib import admin
from .models import Logbook

@admin.register(Logbook)
class LogbookAdmin(admin.ModelAdmin):
    list_display = ('tanggal', 'shift', 'petugas', 'seiscomp_seismik', 'petir', 'waktu_dibuat')
    list_filter = ('tanggal', 'shift', 'seiscomp_seismik')
    search_fields = ('catatan',)