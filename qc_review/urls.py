from django.urls import path
from . import views

app_name = 'qc_review'

urlpatterns = [
    path("", views.event_list, name="event_list"),
    path("event/<str:public_id>/", views.event_detail, name="event_detail"),
    path("event/<str:public_id>/run/<int:run_number>/",
         views.event_detail, name="event_detail_run"),
    path("station/<int:station_id>/review/",
         views.station_review, name="station_review"),

    # Export
    path("export/csv/", views.export_csv, name="export_csv"),
    path("export/pdf/", views.export_pdf, name="export_pdf"),

    # API
    path("api/qc-events/", views.ingest_event, name="ingest_event"),
    path("api/event/<str:public_id>/map.json",
         views.event_map_json, name="event_map_json"),
]
