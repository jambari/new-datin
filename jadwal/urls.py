from django.urls import path
from . import views

urlpatterns = [
    path('', views.tabel_jadwal, name='jadwal_dinas'),
    path('api/generate/', views.generate_auto_schedule, name='api_generate_jadwal'),
    path('api/update/', views.update_jadwal_api, name='api_update_jadwal'),
    path('restore/<int:backup_id>/', views.restore_jadwal, name='restore_jadwal'),
    path('approve-all/', views.approve_all_jadwal, name='approve_all_jadwal'),

    # Pegawai CRUD
    path('pegawai/', views.pegawai_list, name='pegawai_list'),
    path('pegawai/tambah/', views.pegawai_create, name='pegawai_create'),
    path('pegawai/<int:pk>/edit/', views.pegawai_update, name='pegawai_update'),
    path('pegawai/<int:pk>/hapus/', views.pegawai_delete, name='pegawai_delete'),
]