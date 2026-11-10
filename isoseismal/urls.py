from django.urls import path

from . import views

app_name = 'isoseismal'

urlpatterns = [
    path('peta-isoseismal/', views.isoseismal_list, name='list'),
    path('peta-isoseismal/<slug:slug>/', views.isoseismal_detail, name='detail'),
]
