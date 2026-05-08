from django.urls import path
from . import views

urlpatterns = [
    path('api/stations/', views.api_stations, name='api_stations'),
    path('api/stations/push-seismic/', views.api_push_seismic_status, name='api_push_seismic_status'),
]
