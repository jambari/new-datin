from django.contrib import admin
from .models import Layanan


@admin.register(Layanan)
class LayananAdmin(admin.ModelAdmin):
    list_display = ('nama', 'instansi', 'jenis_data', 'status', 'created_at')
    list_filter = ('status', 'jenis_data')
    search_fields = ('nama', 'instansi', 'email', 'jenis_data')
    readonly_fields = ('created_at', 'updated_at')
