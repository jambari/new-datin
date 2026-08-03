from django.contrib import admin
from .models import Guest


@admin.register(Guest)
class GuestAdmin(admin.ModelAdmin):
    list_display = ('nama', 'dari', 'keperluan', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('nama', 'dari', 'keperluan', 'keterangan')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
