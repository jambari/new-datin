from django.urls import path
from . import views

urlpatterns = [
    path('buku-tamu/', views.index, name='guests_index'),
    path('buku-tamu/create/', views.create, name='guests_create'),
    path('buku-tamu/search/', views.search, name='guests_search'),
]
