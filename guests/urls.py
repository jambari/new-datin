from django.urls import path
from . import views

urlpatterns = [
    path('buku-tamu/', views.index, name='guests_index'),
    path('buku-tamu/create/', views.create, name='guests_create'),
    path('buku-tamu/search/', views.search, name='guests_search'),

    # Dashboard CRUD
    path('buku-tamu/dashboard/', views.dashboard_list, name='guests_dashboard_list'),
    path('buku-tamu/dashboard/<int:pk>/delete/', views.dashboard_delete, name='guests_dashboard_delete'),
]
