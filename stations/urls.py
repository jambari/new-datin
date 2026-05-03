from django.urls import path
from . import views

urlpatterns = [
    path('api/stations/', views.api_stations, name='api_stations'),
]
