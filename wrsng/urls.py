from django.urls import path
from .views import (
    WRSNGStatusUpdateAPI, 
    WRSNGStatusListView, 
    wrsng_availability_query,
    update_wrsng_availability # View baru
)


app_name = 'wrsng' # Penting untuk namespacing

urlpatterns = [
    # Endpoint API untuk menerima data
    path('wrsng/status/update/', WRSNGStatusUpdateAPI.as_view(), name='status_update_api'),
    
    # --- URL BARU UNTUK HALAMAN DAFTAR ---
    path('status/list/', WRSNGStatusListView.as_view(), name='status_list'),
    # -----------------------------------
    path('status/report/', wrsng_availability_query, name='wrsng_availability_query'),
    path('api/update-availability/', update_wrsng_availability, name='update_wrsng_availability'),
]
