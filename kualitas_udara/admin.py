from django.contrib import admin

from .models import KAHSeriesData, SPMSeriesData


@admin.register(KAHSeriesData)
class KAHSeriesDataAdmin(admin.ModelAdmin):
    list_display = ("stasiun", "bulan", "minggu", "ph", "dh", "so4", "no3")
    list_filter = ("stasiun", "bulan")
    search_fields = ("stasiun", "bulan")
    ordering = ("-bulan", "-minggu")


@admin.register(SPMSeriesData)
class SPMSeriesDataAdmin(admin.ModelAdmin):
    list_display = ("stasiun", "timestamp", "spm")
    list_filter = ("stasiun", "timestamp")
    search_fields = ("stasiun",)
    ordering = ("-timestamp",)
