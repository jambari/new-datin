from django.urls import path

from . import views

app_name = "reporting"

urlpatterns = [
    path("reporting/", views.index, name="index"),
    path("reporting/laporan/", views.report, name="report"),
    path("reporting/indeks-k/", views.kindex, name="kindex"),
]
