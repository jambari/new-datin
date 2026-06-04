# lightning/urls.py
from django.urls import path
from .views import (
    NexStormQueryView,
    NexStormQueryAPIView,
    StrikeMapDataAPIView,
    lightning_availability_query,
    update_lightning_availability,
    DeleteAllStrikesView,
    lightning_daily_grid_api,
    lightning_monthly_grid_api,
    lightning_grid_dates,
    lightning_grid_months,
    UploadNexStormView,
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
    path('api/map-data/', StrikeMapDataAPIView.as_view(), name='strike_map_data'),
    path('api/update-availability/', update_lightning_availability, name='update_lightning_availability'),

    # --- MAINTENANCE ---
    path('strikes/delete-all/', DeleteAllStrikesView.as_view(), name='strike_delete_all'),
    #path('infographic/', LightningInfographicView.as_view(), name='lightning_infographic'),
    path('api/grid/daily/', lightning_daily_grid_api, name='lightning-daily-grid-api'),
    path('api/grid/monthly/', lightning_monthly_grid_api, name='lightning-monthly-grid-api'),
    path('api/grid/dates/', lightning_grid_dates, name='lightning-grid-dates'),
    path('api/grid/months/', lightning_grid_months, name='lightning-grid-months'),
]
