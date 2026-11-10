from django.contrib import admin, messages
from django.utils.html import format_html

from .models import IsoseismalMap
from .services import generate


@admin.register(IsoseismalMap)
class IsoseismalMapAdmin(admin.ModelAdmin):
    list_display = ('wib_id', 'event_time', 'magnitude', 'lokasi', 'jumlah_dirasakan', 'jumlah_stasiun',
                    'ada_peta', 'is_hidden', 'generated_at')
    list_filter = ('is_hidden',)
    search_fields = ('wib_id', 'lokasi', 'felt_text')
    readonly_fields = ('wib_id', 'slug', 'event_time', 'latitude', 'longitude', 'magnitude', 'depth', 'lokasi',
                       'grid', 'stations', 'observed', 'felt', 'felt_text', 'felt_sources', 'wilayah',
                       'pratinjau', 'generated_at', 'note', 'created_at', 'updated_at')
    fields = ('is_hidden', 'pratinjau', 'wib_id', 'slug', 'event_time', 'magnitude', 'depth', 'latitude',
              'longitude', 'lokasi', 'felt_text', 'felt_sources', 'felt', 'stations', 'observed', 'wilayah',
              'grid', 'generated_at', 'note', 'created_at', 'updated_at')
    actions = ('gambar_ulang', 'sembunyikan', 'tampilkan')

    @admin.display(description='dirasakan')
    def jumlah_dirasakan(self, obj):
        return len(obj.felt)

    @admin.display(description='stasiun')
    def jumlah_stasiun(self, obj):
        return len(obj.stations)

    @admin.display(description='peta', boolean=True)
    def ada_peta(self, obj):
        return bool(obj.image)

    @admin.display(description='peta')
    def pratinjau(self, obj):
        if not obj.image:
            return obj.note or '—'
        return format_html('<a href="{}" target="_blank"><img src="{}" style="max-width:640px;border:1px solid #ccc"></a>'
                           '<br><a href="{}" target="_blank">Halaman publik ↗</a>',
                           obj.image.url, obj.image.url, obj.get_absolute_url())

    @admin.action(description='Gambar ulang peta (cari ulang laporan dirasakan)')
    def gambar_ulang(self, request, queryset):
        for obj in queryset:
            status = generate(obj, force=True)
            self.message_user(request, f'{obj.wib_id}: {status}',
                              messages.SUCCESS if not status.startswith('skip') else messages.WARNING)

    @admin.action(description='Sembunyikan dari publik')
    def sembunyikan(self, request, queryset):
        queryset.update(is_hidden=True)

    @admin.action(description='Tampilkan ke publik')
    def tampilkan(self, request, queryset):
        queryset.update(is_hidden=False)
