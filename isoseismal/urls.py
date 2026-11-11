from django.urls import path

from . import views

app_name = 'isoseismal'

urlpatterns = [
    path('peta-isoseismal/', views.isoseismal_list, name='list'),
    path('peta-isoseismal/<slug:slug>/', views.isoseismal_detail, name='detail'),
    path('peta-isoseismal/<slug:slug>/pdf/', views.isoseismal_pdf, name='pdf'),
    path('peta-isoseismal-skenario/', views.isoseismal_list, {'scenario': True}, name='scenario_list'),
    path('peta-isoseismal-skenario/<slug:slug>/', views.isoseismal_detail, {'scenario': True}, name='scenario_detail'),
    path('peta-isoseismal-skenario/<slug:slug>/pdf/', views.isoseismal_pdf, {'scenario': True}, name='scenario_pdf'),
]
