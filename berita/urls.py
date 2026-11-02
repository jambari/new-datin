from django.urls import path

from . import views

app_name = 'berita'

urlpatterns = [
    # Publik
    path('berita/', views.berita_list, name='list'),
    # Staff (taruh sebelum pola <slug> supaya tidak tertangkap)
    path('berita/tulis/', views.berita_create, name='create'),
    path('berita/kelola/', views.berita_manage, name='manage'),
    path('berita/unggah-gambar/', views.berita_upload_image, name='upload_image'),
    path('berita/<slug:slug>/ubah/', views.berita_update, name='update'),
    path('berita/<slug:slug>/hapus/', views.berita_delete, name='delete'),
    path('berita/<slug:slug>/', views.berita_detail, name='detail'),
]
