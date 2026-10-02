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
]
