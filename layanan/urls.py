from django.urls import path
from . import views

urlpatterns = [
    path('layanan/', views.landing, name='layanan_landing'),
    path('layanan/tentang/', views.tentang, name='layanan_tentang'),
    path('layanan/tarif/', views.tarif, name='layanan_tarif'),
    path('layanan/alur/', views.alur, name='layanan_alur'),
    path('layanan/data/', views.data, name='layanan_data'),
    path('layanan/jasa/', views.jasa, name='layanan_jasa'),
    path('layanan/magang/', views.magang, name='layanan_magang'),
    path('layanan/gts/', views.gts, name='layanan_gts'),
    path('layanan/formulir/<int:id>/', views.formulir, name='layanan_formulir'),
    path('layanan/daftar/', views.daftar, name='layanan_daftar'),

    # Dashboard CRUD
    path('layanan/dashboard/', views.dashboard_list, name='layanan_dashboard_list'),
    path('layanan/dashboard/<int:pk>/', views.dashboard_detail, name='layanan_dashboard_detail'),
]
