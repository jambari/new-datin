# repository/api_urls.py
from django.urls import path
from .views import DataAvailabilityReportView, station_search_api, AcceleroDataAvailabilityView, push_events_api, gempa_laporan_bulanan_api, gempa_dirasakan_api
from wrsng.views import WRSNGStatusUpdateAPI

urlpatterns = [
    path('availability/report/', DataAvailabilityReportView.as_view(), name='availability_report'),
    path('station/search/', station_search_api, name='station_search_api'),
    path('accelero-availability/', AcceleroDataAvailabilityView.as_view(), name='accelero_availability_api'),
    path('events/push/', push_events_api, name='push_events_api'),
    path('gempa/laporan-bulanan/', gempa_laporan_bulanan_api, name='gempa_laporan_bulanan_api'),
    path('gempa/dirasakan/', gempa_dirasakan_api, name='gempa_dirasakan_api'),
    # WRSNG devices post to /api/wrsng/status/update/
    path('wrsng/status/update/', WRSNGStatusUpdateAPI.as_view(), name='wrsng_status_update_api'),
]