from django.contrib import admin
from .models import GempaMemusak, GempaMemusakMedia


class GempaMemusakMediaInline(admin.TabularInline):
    model = GempaMemusakMedia
    extra = 1
    fields = ('file', 'media_type', 'caption')


@admin.register(GempaMemusak)
class GempaMemusakAdmin(admin.ModelAdmin):
    list_display  = ('no', 'tanggal_text', 'wilayah', 'provinsi', 'magnitude', 'depth_km', 'lokasi', 'tsunami', 'sumber')
    list_filter   = ('lokasi', 'tsunami', 'provinsi')
    search_fields = ('tanggal_text', 'wilayah', 'wilayah_merasakan', 'korban_kerusakan')
    ordering      = ('no',)
    inlines       = [GempaMemusakMediaInline]


@admin.register(GempaMemusakMedia)
class GempaMemusakMediaAdmin(admin.ModelAdmin):
    list_display = ('event', 'media_type', 'caption', 'uploaded_at')
    list_filter  = ('media_type',)
