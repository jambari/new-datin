from django.contrib import admin

from .models import FmiIndicesImage


@admin.register(FmiIndicesImage)
class FmiIndicesImageAdmin(admin.ModelAdmin):
    list_display = ('jenis', 'tanggal', 'size_bytes', 'fetched_at', 'telegram_sent_at')
    list_filter = ('jenis', 'tanggal')
    search_fields = ('sha256', 'etag')
    ordering = ('-tanggal', 'jenis')
    readonly_fields = ('fetched_at', 'updated_at', 'sha256', 'size_bytes')
    date_hierarchy = 'tanggal'
