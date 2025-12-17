from django.urls import path
from . import views

app_name = 'logbook'

urlpatterns = [
    # Change the name from 'index' to 'logbook_list' to match the sidebar tag
    path('', views.index, name='logbook_list'), 
    path('print/<int:log_id>/', views.print_log_detail, name='print_log_detail'),
    path('edit/<int:log_id>/', views.edit_log, name='edit_log'),
]