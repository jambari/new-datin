_SKIP_PREFIXES = (
    '/admin/',
    '/static/',
    '/media/',
    '/__reload__/',
    '/favicon',
)

_PATH_LABELS = {
    '/dashboard':           'Dashboard',
    '/repository/events':   'Event Browser',
    '/repository/':         'Repository',
    '/arsip/':              'Arsip Foto',
    '/logbook/':            'Logbook',
    '/perjadin/':           'Perjalanan Dinas',
    '/maintenance/':        'Maintenance',
    '/monitor/':            'Monitor',
    '/hujan/':              'Data Hujan',
    '/lightning/':          'Lightning',
    '/magnet/':             'Geomagnet',
    '/wrsng/':              'WRSNG',
    '/almanac/':            'Almanac',
    '/jadwal/':             'Jadwal',
}


def _label(path, method):
    for prefix, name in _PATH_LABELS.items():
        if path.startswith(prefix):
            return f"{method} {name}"
    return f"{method} {path}"


def _get_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    return xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR')


class ActivityLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only log authenticated POST requests
        if (
            request.method == 'POST'
            and request.user.is_authenticated
            and not any(request.path.startswith(p) for p in _SKIP_PREFIXES)
        ):
            try:
                from .models import ActivityLog
                ActivityLog.objects.create(
                    user=request.user,
                    username=request.user.username,
                    action=ActivityLog.ACTION,
                    path=request.path,
                    description=_label(request.path, 'POST'),
                    ip_address=_get_ip(request),
                )
            except Exception:
                pass  # never break the request due to logging failure

        return response
