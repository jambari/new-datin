# repository/tasks.py

from celery import shared_task
from django.core.management import call_command

@shared_task
def run_process_shakemaps():
    """
    A Celery task to run the process_shakemaps management command.
    """
    print("Starting process_shakemaps task...")
    call_command('process_shakemaps')
    print("Finished process_shakemaps task.")

@shared_task
def fetch_bmkg_felt_task():
    """Fetch BMKG felt earthquakes, filter for Papua, download shakemap images."""
    print("Starting fetch_bmkg_felt task...")
    call_command('fetch_bmkg_felt')
    print("Finished fetch_bmkg_felt task.")


@shared_task
def check_gempa_merusak_task():
    """Daily check: add events with M>=7.0, tsunami warning, or felt >= V MMI."""
    print("Starting check_gempa_merusak task...")
    call_command('check_gempa_merusak', days=2, min_mag=5.5, auto_mag=7.0, min_mmi=5)
    print("Finished check_gempa_merusak task.")