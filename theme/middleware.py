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


class CanonicalHostMiddleware:
    """Arahkan kunjungan halaman lewat alamat IP ke domain resmi (SITE_URL).

    Google sempat mengindeks https://36.91.166.189/ sebagai situs tersendiri. GET/HEAD halaman
    lewat host alias (CANONICAL_ALIAS_HOSTS) dibalas 301 ke domain, sehingga indeks berpindah
    ke domain. API dan permintaan non-GET (skrip pengirim data yang memakai IP) tetap dilayani
    seperti biasa, hanya diberi X-Robots-Tag noindex.
    """

    EXEMPT_PREFIXES = ('/static/', '/media/', '/__reload__/', '/gempa-notify/')

    def __init__(self, get_response):
        from urllib.parse import urlsplit
        from django.conf import settings

        self.get_response = get_response
        site = urlsplit(getattr(settings, 'SITE_URL', '') or '')
        self.base = f'{site.scheme}://{site.netloc}' if site.scheme and site.netloc else ''
        self.aliases = {h.strip().lower() for h in getattr(settings, 'CANONICAL_ALIAS_HOSTS', []) if h.strip()}
        self.aliases.discard((site.hostname or '').lower())

    def _exempt(self, path):
        return '/api/' in path or path.startswith(self.EXEMPT_PREFIXES)

    def __call__(self, request):
        host = request.META.get('HTTP_HOST', '').rsplit(':', 1)[0].strip('[]').lower()
        if not self.base or host not in self.aliases:
            return self.get_response(request)
        if request.method in ('GET', 'HEAD') and not self._exempt(request.path):
            from django.http import HttpResponsePermanentRedirect
            return HttpResponsePermanentRedirect(self.base + request.get_full_path())
        response = self.get_response(request)
        response['X-Robots-Tag'] = 'noindex, nofollow'
        return response
