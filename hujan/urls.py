# hujan/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path('data/hujan/', views.daftar_hujan, name='daftar_hujan'),
    path('data/hujan/query/', views.query_laporan_hujan, name='query_laporan_hujan'), # URL Baru
    path('data/hujan/edit/<int:id>/', views.edit_hujan, name='edit_hujan'),
]