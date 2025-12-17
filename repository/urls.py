from django.urls import path
from . import views
from .views import ShakemapListView, ShakemapDetailView, ShakemapEventDeleteView# Make sure to import the delete view

urlpatterns = [
    # This remains the main page for the app
    path('', views.gempa_list, name='gempa_list'),
    path('detail/<int:pk>/', views.gempa_detail_view, name='gempa_detail'),
    
    # -- SHAKEMAP URLS MODIFIED BELOW --
    path('shakemap/', ShakemapListView.as_view(), name='shakemap-list'),
    path('shakemap/event/<int:pk>/', ShakemapDetailView.as_view(), name='shakemap-detail'),
    
    # This is the new delete URL you need to add
    path('shakemap/delete/<int:pk>/', ShakemapEventDeleteView.as_view(), name='shakemap-delete'),
    path('shakemap/report/', views.shakemap_report_query, name='shakemap_report_query'),
    # Other existing URLs
    path('station_map/', views.station_map_view, name='spicks'),
    path('stations.geojson/', views.station_geojson_api, name='station_geojson'),
    path('station/<str:station_code>/', views.station_detail_view, name='station_detail'),
    path('data-availability/', views.data_availability_list, name='data_availability_list'),
    path('accelero-availability-list/', views.accelero_availability_list, name='accelero_availability_list'),
    path('seismo-availability-query/', views.availability_matrix_view, {'sensor_type': 'seismo'}, name='seismo_availability_query'),
    path('accelero-availability-query/', views.availability_matrix_view, {'sensor_type': 'accelero'}, name='accelero_availability_query'),
    path('api/update-availability/', views.update_availability_cell, name='update_availability_cell'),
]
