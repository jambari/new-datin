from django.urls import path
from . import views

app_name = 'arsip'

urlpatterns = [
    path('arsip/', views.album_list, name='album_list'),
    path('arsip/<int:pk>/', views.album_detail, name='album_detail'),
]
