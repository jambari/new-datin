# repository/api_urls.py
from django.urls import path
from .views import DataAvailabilityReportView, station_search_api, AcceleroDataAvailabilityView

urlpatterns = [
    path('availability/report/', DataAvailabilityReportView.as_view(), name='availability_report'),
    path('station/search/', station_search_api, name='station_search_api'),
    path('accelero-availability/', AcceleroDataAvailabilityView.as_view(), name='accelero_availability_api'),
]