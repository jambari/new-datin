from celery import shared_task

from . import station_report, station_views


@shared_task
def send_station_qc_report_task():
    """Daily station-health report (02:30 UTC): PDF, or a warning if data is missing."""
    station_report.send_daily_report()


@shared_task
def retry_station_qc_report_task():
    """Re-check (04:30 and 06:30 UTC): send the report if the data arrived late."""
    station_report.send_daily_report(retry=True)


@shared_task
def purge_station_media_task():
    """Delete station images older than STATION_MEDIA_KEEP_DAYS; the numbers stay."""
    return station_views.purge_station_media()
