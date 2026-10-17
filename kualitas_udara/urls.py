from django.urls import path

from . import views

app_name = "kualitas_udara"

urlpatterns = [
    # KAH (Kimia Air Hujan)
    path("kualitas-udara/kah/", views.kah_list, name="kah_list"),
    path("kualitas-udara/kah/tambah/", views.kah_create, name="kah_create"),
    path("kualitas-udara/kah/<int:pk>/edit/", views.kah_update, name="kah_update"),
    path("kualitas-udara/kah/<int:pk>/hapus/", views.kah_delete, name="kah_delete"),
    path(
        "kualitas-udara/kah/export/<str:export_format>/",
        views.kah_export,
        name="kah_export",
    ),
    # API impor (token, dipakai cron penarik data dari Database Kualitas Udara BMKG)
    path("kualitas-udara/api/import/", views.api_import, name="api_import"),
    # SPM (Suspended Particulate Matter)
    path("kualitas-udara/spm/", views.spm_list, name="spm_list"),
    path("kualitas-udara/spm/tambah/", views.spm_create, name="spm_create"),
    path("kualitas-udara/spm/<int:pk>/edit/", views.spm_update, name="spm_update"),
    path("kualitas-udara/spm/<int:pk>/hapus/", views.spm_delete, name="spm_delete"),
    path(
        "kualitas-udara/spm/export/<str:export_format>/",
        views.spm_export,
        name="spm_export",
    ),
]
