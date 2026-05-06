from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('landing/', views.landing, name='landing'),
    path('gempa/', views.gempa_public, name='gempa_public'),
    path('kegiatan/', views.our_work, name='our_work'),
]
