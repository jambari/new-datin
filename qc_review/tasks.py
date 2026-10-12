from celery import shared_task
from django.core.management import call_command


@shared_task
def send_station_qc_report_task():
    """Celery wrapper for the send_station_qc_report management command."""
    call_command('send_station_qc_report')
