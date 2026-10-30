from celery import shared_task


@shared_task
def send_permohonan_task(pk):
    from .notify import send_permohonan
    return send_permohonan(pk)
