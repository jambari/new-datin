# repository/api_urls.py
from django.urls import path
from .views import DataAvailabilityReportView, station_search_api, AcceleroDataAvailabilityView, push_events_api, gempa_laporan_bulanan_api, gempa_dirasakan_api, psa5_upload_api, spectrum_json_api, waveform_upload_api, yolo_state_upload_api, yolo_snapshot_upload_api, event_mseed_zip_api
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
    # PSA5 upload: shakemap machine POSTs .psa5 files here
    path('shakemap/psa5/', psa5_upload_api, name='psa5_upload_api'),
    # Waveform upload: shakemap machine POSTs .mseed files, prod renders PNG
    path('shakemap/waveform/', waveform_upload_api, name='waveform_upload_api'),
    # Spectrum JSON: GET design + earthquake PSA for a given event
    path('shakemap/<str:event_id>/spectrum.json', spectrum_json_api, name='spectrum_json_api'),
    # Mseed ZIP: GET all .mseed files + event metadata as a ZIP
    path('shakemap/<str:event_id>/mseed-zip/', event_mseed_zip_api, name='event_mseed_zip_api'),
    # YOLO training state push (private dashboard backend)
    path('yolo/state/', yolo_state_upload_api, name='yolo_state_upload_api'),
    # YOLO weight snapshot push (best.pt / last.pt)
    path('yolo/snapshot/', yolo_snapshot_upload_api, name='yolo_snapshot_upload_api'),
]