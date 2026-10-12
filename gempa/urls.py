"""URL aplikasi gempa.

Admin site-nya tidak di sini — didaftarkan di datin_project/urls.py pada prefix
/gempa-admin/ (lihat gempa/sites.py). Yang di sini hanya endpoint pendukung.
"""
from django.urls import path

from . import views

app_name = 'gempa'

urlpatterns = [
    # Dipanggil berkala oleh static/js/gempa_notify.js dari tiap halaman admin.
    path('gempa-notify/latest/', views.latest_event_notify, name='notify-latest'),

    # Tombol "Laporan Bulanan" & "Gempa Susulan" (admin/gempa/change_list.html).
    path('laporan-bulanan/', views.laporan_bulanan, name='laporan-bulanan'),
    path('gempa-susulan/', views.gempa_susulan, name='gempa-susulan'),
    path('gempa-susulan/focal/save/', views.focal_save, name='focal-save'),
    path('gempa-susulan/focal/position/save/', views.focal_position_save,
         name='focal-position-save'),
]
