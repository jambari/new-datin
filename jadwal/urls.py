from django.urls import path
from . import views

urlpatterns = [
    path('', views.tabel_jadwal, name='jadwal_dinas'),
    path('api/generate/', views.generate_auto_schedule, name='api_generate_jadwal'),
    path('api/update/', views.update_jadwal_api, name='api_update_jadwal'),
    path('restore/<int:backup_id>/', views.restore_jadwal, name='restore_jadwal'),
]