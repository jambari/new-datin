from django.urls import path
from . import views

app_name = 'maintenance'

urlpatterns = [
    # Dashboard & Lists
    path('', views.maintenance_dashboard, name='dashboard'),
    path('alat/', views.instrument_list, name='instrument_list'),
    path('tiket/', views.issue_list, name='issue_list'),

    # CRUD Instrument
    path('alat/tambah/', views.instrument_create, name='instrument_create'),
    path('alat/<int:pk>/edit/', views.instrument_update, name='instrument_update'),
    path('alat/<int:pk>/hapus/', views.instrument_delete, name='instrument_delete'),

    # CRUD Issue
    path('tiket/tambah/', views.issue_create, name='issue_create'),
    path('tiket/<int:pk>/edit/', views.issue_update, name='issue_update'),
    path('tiket/<int:pk>/hapus/', views.issue_delete, name='issue_delete'),
]