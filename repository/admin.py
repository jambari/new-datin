from django.contrib import admin
from .models import GempaMemusak


@admin.register(GempaMemusak)
class GempaMemusakAdmin(admin.ModelAdmin):
    list_display = ('no', 'tanggal_text', 'wilayah', 'magnitude', 'depth_km', 'lokasi', 'tsunami', 'sumber')
    list_filter = ('lokasi', 'tsunami')
    search_fields = ('tanggal_text', 'wilayah', 'wilayah_merasakan', 'korban_kerusakan')
    ordering = ('no',)
