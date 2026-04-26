# repository/api_urls.py
from django.urls import path
from .views import DataAvailabilityReportView, station_search_api, AcceleroDataAvailabilityView, push_events_api

urlpatterns = [
    path('availability/report/', DataAvailabilityReportView.as_view(), name='availability_report'),
    path('station/search/', station_search_api, name='station_search_api'),
    path('accelero-availability/', AcceleroDataAvailabilityView.as_view(), name='accelero_availability_api'),
    path('events/push/', push_events_api, name='push_events_api'),
]