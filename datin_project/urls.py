"""
URL configuration for datin_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from repository.views import station_map_view 
from django.conf import settings #
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path("__reload__/", include("django_browser_reload.urls")), 
    path('', include('monitor.urls')),
    path('', include('theme.urls')),
    path('repository/', include('repository.urls')),
    path('api/', include('repository.api_urls')),
    path('magnet/', include('magnet.urls')),
    path('', include('hujan.urls')),
    path('', include('almanac.urls')),
    path('lightning/', include('lightning.urls')),
    path('wrsng/', include('wrsng.urls')),
    path('api/', include('wrsng.urls')),
    path('logbook/', include('logbook.urls')),
    path('jadwal/', include('jadwal.urls')),
    path('maintenance/', include('maintenance.urls')),
]

# This tells Django to serve media files during development
if settings.DEBUG:
    urlpatterns = static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) + urlpatterns