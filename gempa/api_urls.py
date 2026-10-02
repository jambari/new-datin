"""URL API katalog gempa (di-mount di /api/gempa/)."""
from django.urls import path

from .api_ingest import ingest_event

urlpatterns = [
    # Ingest event dari SeisComp (host 192.168.1.7 -> exportevent.sh).
    # Body = isi mentah mailexportfile.txt, auth: Authorization: Bearer <token>.
    path('ingest/<str:region>/', ingest_event, name='gempa-ingest'),
]
