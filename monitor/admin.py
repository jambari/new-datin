from django.contrib import admin
from .models import EarthquakeEvent

@admin.register(EarthquakeEvent)
class EarthquakeEventAdmin(admin.ModelAdmin):
    list_display = ('event_id', 'origin_time', 'magnitude', 'region', 'agency', 'depth')
    list_filter = ('agency', 'event_type', 'status', 'origin_time')
    search_fields = ('event_id', 'region')
    ordering = ('-origin_time',)