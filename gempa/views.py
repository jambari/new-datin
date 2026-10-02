"""Endpoint notifikasi katalog gempa.

Hanya `latest_event_notify` yang diport dari views.py .188 (dipakai oleh
static/js/gempa_notify.js di setiap halaman changelist admin).
Halaman lain di views.py .188 (laporan-bulanan, gempa-susulan, catalog-compare)
di luar scope port ini.
"""
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from .models import (Gempa, Balaigempa, Gempasorong, Gempanabire,
                     Satudatagempa, Significant)

# Urutan: model_key -> (Model, nama URL di namespace gempa_admin, field keterangan)
_NOTIFY_CONFIG = {
    'gempa':         (Gempa,         'gempa_admin:gempa-template-balai',       'ket'),
    'balaigempa':    (Balaigempa,    'gempa_admin:balaigempa-sms',             'ket'),
    'gempasorong':   (Gempasorong,   'gempa_admin:gempasorong-info',           'ket'),
    'gempanabire':   (Gempanabire,   'gempa_admin:gempanabire-info',           'ket'),
    'satudatagempa': (Satudatagempa, 'gempa_admin:gempa_satudatagempa_change', 'ket'),
    'significant':   (Significant,   'gempa_admin:significant-template',       'ket'),
}


def latest_event_notify(request):
    """JSON event terbaru untuk satu model — dipanggil berkala oleh gempa_notify.js."""
    model_key = request.GET.get('model', '')
    if model_key not in _NOTIFY_CONFIG:
        return JsonResponse({'error': 'unknown model'}, status=400)

    Model, url_name, ket_field = _NOTIFY_CONFIG[model_key]
    obj = Model.objects.order_by('-created_at').first()
    if not obj:
        return JsonResponse({'id': None})

    try:
        tmpl_url = reverse(url_name, args=[obj.pk])
    except Exception:
        tmpl_url = '#'

    return JsonResponse({
        'id':         obj.pk,
        'created_at': obj.created_at.isoformat() if obj.created_at else None,
        'mag':        str(obj.magnitudo),
        'ket':        getattr(obj, ket_field, '') or '',
        'template_url': tmpl_url,
    })


# Nama grup pemilik akses katalog (dibuat oleh migrasi 0002_operator_group).
KATALOG_GROUP_NAME = 'Operator Katalog Gempa'


def post_login_redirect(request):
    """Tujuan setelah login tanpa parameter ?next=.

    User yang hanya anggota grup "Operator Katalog Gempa" diarahkan ke
    /gempa-admin/ (admin katalog, tanpa OTP). Semua user lain tetap ke
    halaman biasa (POST_LOGIN_REDIRECT_URL, default /dashboard/).
    """
    if not request.user.is_authenticated:
        return redirect(settings.LOGIN_URL)

    group_names = set(request.user.groups.values_list('name', flat=True))
    if KATALOG_GROUP_NAME in group_names and not request.user.is_superuser:
        return redirect('gempa_admin:index')

    return redirect(settings.POST_LOGIN_REDIRECT_URL)

