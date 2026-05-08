from django.conf import settings


def seo(request):
    return {
        'GA_MEASUREMENT_ID': getattr(settings, 'GA_MEASUREMENT_ID', ''),
        'SITE_URL':          getattr(settings, 'SITE_URL', ''),
        'SITE_NAME':         'Stasiun Geofisika Kelas I Jayapura · BMKG',
    }
