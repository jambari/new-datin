from django.contrib import admin

# Register your models here.
from .models import SunMoonEvent

@admin.register(SunMoonEvent)
class SunMoonEventAdmin(admin.ModelAdmin):
    list_display = ('date', 'city', 'sun_rise', 'sun_set', 'moon_rise', 'moon_set', 'moon_phase')
    list_filter = ('city',)