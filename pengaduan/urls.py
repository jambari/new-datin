from django.urls import path
from . import views

urlpatterns = [
    path('pengaduan/', views.form, name='pengaduan_form'),
    path('pengaduan/success/', views.success, name='pengaduan_success'),
    path('pengaduan/list/', views.pengaduan_list, name='pengaduan_list'),
]
