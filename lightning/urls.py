# lightning/urls.py
from django.urls import path
from .views import (
    NexStormQueryView,
    NexStormQueryAPIView,
    lightning_availability_query,
    update_lightning_availability,
    DeleteAllStrikesView,
    UploadNexStormView,
    #LightningInfographicView,  # <--- TAMBAHKAN INI
)

app_name = 'lightning'

urlpatterns = [
    # --- PAGE 1: Dashboard ---
    path('query/', NexStormQueryView.as_view(), name='nexstorm_query_page'),
    
    # --- PAGE 2: Availability Matrix ---
    path('availability/', lightning_availability_query, name='lightning_availability_query'),

    # --- PAGE 3: Upload Data (New) ---
    path('upload/', UploadNexStormView.as_view(), name='upload_nexstorm'),

    # --- API ENDPOINTS ---
    path('api/query/', NexStormQueryAPIView.as_view(), name='nexstorm_query_api'),
    path('api/update-availability/', update_lightning_availability, name='update_lightning_availability'),

    # --- MAINTENANCE ---
    path('strikes/delete-all/', DeleteAllStrikesView.as_view(), name='strike_delete_all'),
    #path('infographic/', LightningInfographicView.as_view(), name='lightning_infographic'),
]
