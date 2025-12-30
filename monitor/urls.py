from django.urls import path
from . import views

urlpatterns = [
    path('monitor/', views.public_event_list, name='public_event_list'),
    path('api/receive/', views.receive_event_data, name='receive_event'),
    path('monitor/json/', views.export_all_json, name='export_json'),
    path('monitor/webgis/<str:event_id>/', views.webgis_event_detail, name='webgis_detail'),
    path('monitor/analisis/', views.seismicity_analysis, name='seismicity_analysis'),

]