"""Halaman publik peta isoseismal (/peta-isoseismal/)."""
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from .felt import roman
from .layout import SCALE, band
from .models import IsoseismalMap

PER_PAGE = 12


def isoseismal_list(request):
    page = Paginator(IsoseismalMap.objects.public(), PER_PAGE).get_page(request.GET.get('page', 1))
    return render(request, 'isoseismal/list.html', {'page_obj': page, 'maps': page.object_list})


def _band(mmi):
    if mmi is None:
        return None
    row = SCALE[band(mmi)]
    return {'label': row[0], 'color': row[3], 'desc': row[4]}


def isoseismal_detail(request, slug):
    from gempa.faults import sumber_terdekat_baris

    obj = get_object_or_404(IsoseismalMap, slug=slug)
    is_public = IsoseismalMap.objects.public().filter(pk=obj.pk).exists()
    if not is_public and not (request.user.is_authenticated and request.user.is_staff):
        raise Http404('Peta isoseismal tidak ditemukan.')
    felt = [dict(f, band=_band(f['mmi'])) for f in obj.felt]
    stations = [dict(s, band=_band(s.get('mmi')), roman=roman(s.get('mmi'))) for s in obj.stations]
    wilayah = [dict(w, band=_band(w['mmi'])) for w in obj.wilayah if w['mmi'] >= 1.5]
    return render(request, 'isoseismal/detail.html', {
        'obj': obj,
        'is_public': is_public,
        'felt': felt,
        'stations': stations,
        'wilayah': wilayah,
        'mmi_max': _band(obj.mmi_max),
        'sumber': sumber_terdekat_baris(obj.latitude, obj.longitude, obj.depth),
        'others': IsoseismalMap.objects.public().exclude(pk=obj.pk)[:3],
        'share_url': request.build_absolute_uri(obj.get_absolute_url()),
    })
