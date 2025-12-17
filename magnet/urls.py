# magnet/urls.py
from django.urls import path
from . import views
from .views import (
    SummaryView, PrecursorCreateView, PrecursorUpdateView, 
    PrecursorDeleteView, PrecursorDetailView, validate_single_precursor, update_magnet_availability, magnet_availability_query
)
# app_name = 'magnet'
urlpatterns = [
    path('observation/', views.observation_form_view, name='observation_form'),
    path('records/', views.observation_list_view, name='observation_list'),
    path('result/', views.conversion_result_view, name='conversion_result'),
    path('records/<int:pk>/', views.observation_detail_view, name='observation_detail'),
    path('records/<int:pk>/edit/', views.observation_edit_view, name='observation_edit'), # Add this
    path('records/<int:pk>/automate/', views.trigger_single_automation_view, name='trigger_single_automation'), 
    path('trigger-automation/', views.trigger_automation_view, name='trigger_automation'),
    path('result/', views.conversion_result_view, name='conversion_result'),
    path('records/<int:pk>/delete/', views.observation_delete_view, name='observation_delete'),
    path('dim-calculator/', views.dim_calculator_view, name='dim_calculator'),
    path('precursor/', SummaryView.as_view(), name='precursor_list'),
    path('precursor/add/', PrecursorCreateView.as_view(), name='add_precursor'),
    path('precursor/<int:pk>/edit/', PrecursorUpdateView.as_view(), name='precursor_edit'),
    
    # URL untuk hapus prekursor
    path('precursor/<int:pk>/delete/', PrecursorDeleteView.as_view(), name='precursor_delete'),
    
    # URL untuk memicu validasi satu prekursor
    path('precursor/<int:pk>/validate/', validate_single_precursor, name='precursor_validate'),
    path('precursor/<int:pk>/', PrecursorDetailView.as_view(), name='precursor_detail'),
    path('availability-query/', magnet_availability_query, name='magnet_availability_query'),
    path('api/update-availability/', update_magnet_availability, name='update_magnet_availability'),
    
]