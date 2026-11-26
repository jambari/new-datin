from celery import shared_task
from django.core.management import call_command


@shared_task
def send_birthday_wishes_task():
    """Celery wrapper for the send_birthday_wishes management command."""
    print("Starting send_birthday_wishes task...")
    call_command('send_birthday_wishes')
    print("Finished send_birthday_wishes task.")


@shared_task
def notify_jadwal_change_task(text):
    """Kabarkan perubahan pola dinas ke grup Telegram (tidak pernah melempar exception)."""
    from django.conf import settings
    from theme.telegram import send_telegram_message
    send_telegram_message(text, chat_id=getattr(settings, 'JADWAL_TELEGRAM_CHAT_ID', '') or None)
