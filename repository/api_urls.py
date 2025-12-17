# repository/api_urls.py
from django.urls import path
from .views import DataAvailabilityReportView, station_search_api, AcceleroDataAvailabilityView, GempaCreateAPIView
# from .views import station_search_api

urlpatterns = [
    path('availability/report/', DataAvailabilityReportView.as_view(), name='availability_report'),
    path('station/search/', station_search_api, name='station_search_api'), # Tambahkan ini
    path('accelero-availability/', AcceleroDataAvailabilityView.as_view(), name='accelero_availability_api'),
    path('gempa/create/', GempaCreateAPIView.as_view(), name='gempa_create_api'), 
]