# almanac/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('events/', views.eventmoon_list, name='event_list'),
    path('report/', views.sunmoon_monthly_report, name='sunmoon_report'),
]
