from django.urls import path
from . import views
from repository.views import yolo_progress_view, yolo_download_view

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('', views.landing, name='landing'),
    path('gempa/', views.gempa_public, name='gempa_public'),
    path('gempa/<str:public_id>/', views.public_gempa_detail, name='public_gempa_detail'),
    path('gempa-merusak/', views.public_gempa_merusak, name='public_gempa_merusak'),
    path('shakemap/', views.public_shakemap_list, name='public_shakemap_list'),
    path('spectra-acceleration/', views.public_spectra_list, name='public_spectra_list'),
    path('shakemap/<int:pk>/', views.public_shakemap_detail, name='public_shakemap_detail'),
    path('shakemap/<int:pk>/spectrum/', views.public_shakemap_spectrum, name='public_shakemap_spectrum'),
    path('kegiatan/', views.our_work, name='our_work'),
    path('magnetbumi/', views.public_magnetbumi, name='public_magnetbumi'),
    path('magnetbumi/data/', views.public_magnetbumi_data, name='public_magnetbumi_data'),
    path('petir/', views.public_petir, name='public_petir'),
    path('petir/data/', views.public_petir_data, name='public_petir_data'),
    path('tentang/', views.public_about, name='public_about'),
    path('glosarium/', views.public_glosarium, name='public_glosarium'),
    path('peringatan-dini/', views.public_peringatan_dini_data, name='public_peringatan_dini_data'),
    path('poster/', views.poster_datin, name='poster_datin'),
    # Private (jambari-only) YOLO training progress dashboard
    path('yolo-progress/', yolo_progress_view, name='yolo_progress'),
    path('yolo-progress/download/<str:key>', yolo_download_view, name='yolo_download'),
    path('buletin/', views.public_bulletin_list, name='public_bulletin_list'),
    path('buletin/<int:pk>/', views.public_bulletin_detail, name='public_bulletin_detail'),
    path('siaran-pers/', views.public_siaranpress_list, name='public_siaranpress_list'),
    path('siaran-pers/<int:pk>/', views.public_siaranpress_detail, name='public_siaranpress_detail'),
]
