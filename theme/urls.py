from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('landing/', views.landing, name='landing'),
    path('gempa/', views.gempa_public, name='gempa_public'),
    path('gempa/<str:public_id>/', views.public_gempa_detail, name='public_gempa_detail'),
    path('shakemap/', views.public_shakemap_list, name='public_shakemap_list'),
    path('shakemap/<int:pk>/', views.public_shakemap_detail, name='public_shakemap_detail'),
    path('kegiatan/', views.our_work, name='our_work'),
    path('magnetbumi/', views.public_magnetbumi, name='public_magnetbumi'),
    path('magnetbumi/data/', views.public_magnetbumi_data, name='public_magnetbumi_data'),
    path('petir/', views.public_petir, name='public_petir'),
    path('petir/data/', views.public_petir_data, name='public_petir_data'),
    path('tentang/', views.public_about, name='public_about'),
]
