from celery import shared_task
from django.core.management import call_command


@shared_task
def send_birthday_wishes_task():
    """Celery wrapper for the send_birthday_wishes management command."""
    print("Starting send_birthday_wishes task...")
    call_command('send_birthday_wishes')
    print("Finished send_birthday_wishes task.")
