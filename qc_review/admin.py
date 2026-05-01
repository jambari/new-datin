from django.contrib import admin
from .models import Event, QCRun, StationResult


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("public_id", "origin_time", "magnitude",
                    "region", "run_count")
    search_fields = ("public_id", "region")


@admin.register(QCRun)
class QCRunAdmin(admin.ModelAdmin):
    list_display = ("event", "run_number", "committed_at")
    list_filter = ("committed_at",)
    search_fields = ("event__public_id",)


@admin.register(StationResult)
class StationResultAdmin(admin.ModelAdmin):
    list_display = ("run", "network", "station", "distance_class",
                    "qc_flag", "delta_p", "delta_s", "reviewer_action")
    list_filter = ("qc_flag", "distance_class", "reviewer_action")
    search_fields = ("run__event__public_id", "station")
