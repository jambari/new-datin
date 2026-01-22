from django.urls import path
from . import views

app_name = 'perjadin'
urlpatterns = [
    path('', views.index_perjadin, name='index_perjadin'),
    path('tambah/', views.tambah_perjadin, name='tambah_perjadin'),
    path('detail/<int:pegawai_id>/', views.detail_pegawai, name='detail_perjadin'),
]