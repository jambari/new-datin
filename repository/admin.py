from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Bulletin,
    EventResponseSpectrum,
    EventStationWaveform,
    FeltEarthquake,
    GempaMemusak,
    GempaMemusakMedia,
    ShakemapEvent,
    SiaranPress,
    Station,
    StationDesignSpectrum,
)


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


# ---------------------------------------------------------------------------
# Shakemap-related models — registered so the BMKG-felt sync and the .50 PUSH
# can be inspected / spot-corrected from /admin/.
# ---------------------------------------------------------------------------

@admin.register(ShakemapEvent)
class ShakemapEventAdmin(admin.ModelAdmin):
    list_display       = ('event_id', 'event_time', 'magnitude', 'depth', 'location_string', 'has_image')
    list_filter        = ('event_time',)
    search_fields      = ('event_id', 'location_string')
    ordering           = ('-event_time',)
    date_hierarchy     = 'event_time'
    readonly_fields    = ('shakemap_preview',)
    fields             = ('event_id', 'event_time', 'latitude', 'longitude', 'magnitude', 'depth',
                          'location_string', 'shakemap_image', 'shakemap_preview')

    @admin.display(boolean=True, description='image')
    def has_image(self, obj):
        return bool(obj.shakemap_image)

    @admin.display(description='Preview')
    def shakemap_preview(self, obj):
        if not obj.shakemap_image:
            return '—'
        return format_html('<img src="{}" style="max-height:400px; max-width:100%;">',
                           obj.shakemap_image.url)


@admin.register(FeltEarthquake)
class FeltEarthquakeAdmin(admin.ModelAdmin):
    list_display    = ('event_datetime', 'magnitude', 'depth_km', 'wilayah', 'dirasakan', 'fetched_at')
    list_filter     = ('event_datetime', 'fetched_at')
    search_fields   = ('wilayah', 'dirasakan')
    ordering        = ('-event_datetime',)
    date_hierarchy  = 'event_datetime'
    readonly_fields = ('fetched_at',)


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display  = ('code', 'network', 'name', 'latitude', 'longitude', 'elevation')
    list_filter   = ('network',)
    search_fields = ('code', 'name')
    ordering      = ('code',)


@admin.register(StationDesignSpectrum)
class StationDesignSpectrumAdmin(admin.ModelAdmin):
    list_display    = ('station', 'pga', 'ss', 's1', 'tl', 'fetched_at')
    search_fields   = ('station__code', 'station__name')
    autocomplete_fields = ('station',)
    readonly_fields = ('fetched_at',)


@admin.register(EventResponseSpectrum)
class EventResponseSpectrumAdmin(admin.ModelAdmin):
    list_display    = ('event_id', 'station_code', 'component', 'spectrum_points', 'uploaded_at')
    list_filter     = ('component', 'uploaded_at')
    search_fields   = ('event_id', 'station_code')
    ordering        = ('-uploaded_at',)
    readonly_fields = ('uploaded_at',)

    @admin.display(description='points')
    def spectrum_points(self, obj):
        try:
            return len(obj.spectrum)
        except (TypeError, AttributeError):
            return '—'


@admin.register(EventStationWaveform)
class EventStationWaveformAdmin(admin.ModelAdmin):
    list_display    = ('event_id', 'station_code', 'component', 'has_image', 'uploaded_at')
    list_filter     = ('component', 'uploaded_at')
    search_fields   = ('event_id', 'station_code')
    ordering        = ('-uploaded_at',)
    readonly_fields = ('uploaded_at', 'waveform_preview')
    fields          = ('event_id', 'station_code', 'component', 'image', 'waveform_preview', 'uploaded_at')

    @admin.display(boolean=True, description='image')
    def has_image(self, obj):
        return bool(obj.image)

    @admin.display(description='Preview')
    def waveform_preview(self, obj):
        if not obj.image:
            return '—'
        return format_html('<img src="{}" style="max-height:240px; max-width:100%;">',
                           obj.image.url)


@admin.register(Bulletin)
class BulletinAdmin(admin.ModelAdmin):
    list_display  = ('title', 'bulan', 'tahun', 'created_at')
    list_filter   = ('tahun', 'bulan')
    search_fields = ('title',)
    ordering      = ('-tahun', '-bulan')


@admin.register(SiaranPress)
class SiaranPressAdmin(admin.ModelAdmin):
    list_display  = ('title', 'author', 'created_at')
    list_filter   = ('author',)
    search_fields = ('title', 'author')
    ordering      = ('-created_at',)
