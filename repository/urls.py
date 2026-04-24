from django.urls import path
from . import views
from .views import ShakemapListView, ShakemapDetailView, ShakemapEventDeleteView# Make sure to import the delete view

urlpatterns = [
    # This remains the main page for the app
    path('', views.gempa_list, name='gempa_list'),
    path('detail/<int:pk>/', views.gempa_detail_view, name='gempa_detail'),
    path('edit/<int:pk>/', views.gempa_edit, name='gempa_edit'),
    path('delete/<int:pk>/', views.gempa_delete, name='gempa_delete'),
    
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
    path('json/upload/', views.json_upload_create, name='json_upload_create'),
    path('json/list/', views.json_upload_list, name='json_upload_list'),
    path('json/analysis/<int:pk>/', views.json_analysis, name='json_analysis'),
    path('json/delete/<int:pk>/', views.json_delete, name='json_delete'),

    path('event-browser/', views.event_browser, name='event_browser'),

    # ── Gempa Merusak CRUD ─────────────────────────────────────────────────────
    path('gempa-merusak/', views.gempa_merusak_list, name='gempa_merusak_list'),
    path('gempa-merusak/tambah/', views.gempa_merusak_create, name='gempa_merusak_create'),
    path('gempa-merusak/<int:pk>/', views.gempa_merusak_detail, name='gempa_merusak_detail'),
    path('gempa-merusak/<int:pk>/edit/', views.gempa_merusak_update, name='gempa_merusak_update'),
    path('gempa-merusak/<int:pk>/hapus/', views.gempa_merusak_delete, name='gempa_merusak_delete'),
]
