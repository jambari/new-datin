from django.contrib import admin
from .models import Event, QCRun, StationDailyQC, StationDiagnosis, StationQCReport, StationResult


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


@admin.register(StationDailyQC)
class StationDailyQCAdmin(admin.ModelAdmin):
    list_display = ("day", "network", "station", "location", "channel", "status")
    list_filter = ("status", "network", "day")
    search_fields = ("station",)
    date_hierarchy = "day"


@admin.register(StationDiagnosis)
class StationDiagnosisAdmin(admin.ModelAdmin):
    list_display = ("day", "network", "station", "channel", "code", "severity")
    list_filter = ("severity", "code", "day")
    search_fields = ("station", "message_id", "message_en")
    date_hierarchy = "day"


@admin.register(StationQCReport)
class StationQCReportAdmin(admin.ModelAdmin):
    list_display = ("day", "status", "sent_at", "updated_at")
    list_filter = ("status",)
