from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver


def _get_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    return xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR')


@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    from .models import ActivityLog
    ActivityLog.objects.create(
        user=user,
        username=user.username,
        action=ActivityLog.LOGIN,
        path=request.path,
        description=f"Login berhasil",
        ip_address=_get_ip(request),
    )


@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs):
    from .models import ActivityLog
    if user:
        ActivityLog.objects.create(
            user=user,
            username=user.username,
            action=ActivityLog.LOGOUT,
            path=request.path,
            description="Logout",
            ip_address=_get_ip(request),
        )
