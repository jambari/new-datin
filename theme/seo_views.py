"""Berkas di akar situs yang diminta mesin pencari dan peramban: favicon dan web manifest."""
from django.http import HttpResponsePermanentRedirect, JsonResponse
from django.templatetags.static import static
from django.views.decorators.cache import cache_control

SITE_NAME = 'Stasiun Geofisika Kelas I Jayapura · BMKG'


def absolute_url(request, path):
    """URL lengkap di domain resmi (SITE_URL), bukan host permintaan (bisa alamat IP):
    dipakai untuk canonical, tautan bagikan, dan PDF."""
    from django.conf import settings
    base = (getattr(settings, 'SITE_URL', '') or '').rstrip('/')
    return base + path if base else request.build_absolute_uri(path)


def static_redirect(path):
    """/favicon.ico dan /apple-touch-icon.png di akar situs → berkas statis (nama ber-hash)."""
    @cache_control(public=True, max_age=86400)
    def view(request):
        return HttpResponsePermanentRedirect(static(path))
    return view


@cache_control(public=True, max_age=86400)
def webmanifest(request):
    icon = lambda name, size, purpose='any': {
        'src': static(f'theme/favicon/{name}'), 'sizes': size, 'type': 'image/png', 'purpose': purpose}
    return JsonResponse({
        'name': SITE_NAME,
        'short_name': 'BMKG Jayapura',
        'description': 'Informasi gempabumi, shakemap, peta isoseismal, magnetbumi, dan petir wilayah Papua.',
        'lang': 'id',
        'start_url': '/',
        'scope': '/',
        'display': 'browser',
        'background_color': '#ffffff',
        'theme_color': '#0b3d91',
        'icons': [icon('favicon-192.png', '192x192'), icon('favicon-512.png', '512x512'),
                  icon('maskable-512.png', '512x512', 'maskable')],
    }, content_type='application/manifest+json', json_dumps_params={'ensure_ascii': False})
