from django.urls import path

from . import views

app_name = "monitoring_pm"

urlpatterns = [
    path("", views.index, name="index"),
    path("peralatan/", views.peralatan_list, name="peralatan_list"),
    path("peralatan/tambah/", views.peralatan_create, name="peralatan_create"),
    path("peralatan/<int:pk>/edit/", views.peralatan_update, name="peralatan_update"),
    path("peralatan/<int:pk>/hapus/", views.peralatan_delete, name="peralatan_delete"),
    path("peminjaman/", views.peminjaman_list, name="peminjaman_list"),
    path("peminjaman/tambah/", views.peminjaman_create, name="peminjaman_create"),
    path("peminjaman/<int:pk>/edit/", views.peminjaman_update, name="peminjaman_update"),
    path("peminjaman/<int:pk>/hapus/", views.peminjaman_delete, name="peminjaman_delete"),
    path("peminjaman/unduh-data/", views.peminjaman_unduh_data, name="peminjaman_unduh_data"),
    path("laporan/", views.laporan_list, name="laporan_list"),
    path("suku-cadang/peralatan/", views.suku_cadang_peralatan_list, name="suku_cadang_peralatan_list"),
    path("suku-cadang/peralatan/tambah/", views.suku_cadang_peralatan_create, name="suku_cadang_peralatan_create"),
    path("suku-cadang/peralatan/<int:pk>/edit/", views.suku_cadang_peralatan_update, name="suku_cadang_peralatan_update"),
    path("suku-cadang/peralatan/<int:pk>/hapus/", views.suku_cadang_peralatan_delete, name="suku_cadang_peralatan_delete"),
    path("suku-cadang/manajemen/", views.suku_cadang_manajemen_list, name="suku_cadang_manajemen_list"),
    path("suku-cadang/manajemen/tambah/", views.suku_cadang_manajemen_create, name="suku_cadang_manajemen_create"),
    path("suku-cadang/manajemen/<int:pk>/edit/", views.suku_cadang_manajemen_update, name="suku_cadang_manajemen_update"),
    path("suku-cadang/manajemen/<int:pk>/hapus/", views.suku_cadang_manajemen_delete, name="suku_cadang_manajemen_delete"),
    path("suku-cadang/unduh-data/", views.suku_cadang_unduh_data, name="suku_cadang_unduh_data"),
]
