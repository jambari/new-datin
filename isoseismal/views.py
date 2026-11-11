"""Halaman publik peta isoseismal (/peta-isoseismal/)."""
from django.core.paginator import Paginator
from django.db.models import Q, TextField
from django.db.models.functions import Cast
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.text import slugify

from .felt import roman
from .layout import SCALE, band
from .models import IsoseismalMap

PER_PAGE = 12


def search(qs, q):
    """Cari nama tempat/kota: lokasi katalog (juga yang ditulis tanpa spasi, mis. KEBARMANOKWARI),
    judul (slug), teks dan titik laporan dirasakan, serta nama kabupaten/kota."""
    q = q.strip()
    if not q:
        return qs
    cond = Q(lokasi__icontains=q) | Q(lokasi__icontains=q.replace(' ', '')) | Q(felt_text__icontains=q)
    if slugify(q):
        cond |= Q(slug__icontains=slugify(q))
    return (qs.annotate(_felt=Cast('felt', TextField()), _wilayah=Cast('wilayah', TextField()))
              .filter(cond | Q(_felt__icontains=q) | Q(_wilayah__icontains=q)))


def _public(scenario):
    return IsoseismalMap.objects.public_scenarios() if scenario else IsoseismalMap.objects.public()


def isoseismal_list(request, scenario=False):
    q = request.GET.get('q', '').strip()
    page = Paginator(search(_public(scenario), q), PER_PAGE).get_page(request.GET.get('page', 1))
    return render(request, 'isoseismal/list.html',
                  {'page_obj': page, 'maps': page.object_list, 'query': q, 'scenario': scenario})


def _band(mmi):
    if mmi is None:
        return None
    row = SCALE[band(mmi)]
    return {'label': row[0], 'color': row[3], 'desc': row[4]}


def _get_visible(request, slug, scenario):
    obj = get_object_or_404(IsoseismalMap, slug=slug, is_scenario=scenario)
    is_public = _public(scenario).filter(pk=obj.pk).exists()
    if not is_public and not (request.user.is_authenticated and request.user.is_staff):
        raise Http404('Peta isoseismal tidak ditemukan.')
    return obj, is_public


def _content(obj):
    """Isi penjelasan yang sama untuk halaman web dan PDF."""
    from gempa.faults import sumber_terdekat_baris
    from gempa.tektonik import SUMBER as TEKTONIK_SUMBER, ringkasan_tektonik

    return {
        'felt': [dict(f, band=_band(f['mmi'])) for f in obj.felt],
        'stations': [dict(s, band=_band(s.get('mmi')), roman=roman(s.get('mmi'))) for s in obj.stations],
        'wilayah': [dict(w, band=_band(w['mmi'])) for w in obj.wilayah if w['mmi'] >= 1.5],
        'mmi_max': _band(obj.mmi_max),
        'sumber': sumber_terdekat_baris(obj.latitude, obj.longitude, obj.depth),
        # skenario: waktu rekaan, jadi semua gempa terdahulu boleh disebut
        'tektonik': ringkasan_tektonik(obj.latitude, obj.longitude, obj.depth,
                                       None if obj.is_scenario else obj.wit_time.date()),
        'tektonik_sumber': TEKTONIK_SUMBER,
    }


def isoseismal_detail(request, slug, scenario=False):
    obj, is_public = _get_visible(request, slug, scenario)
    return render(request, 'isoseismal/detail.html', {
        'obj': obj,
        'is_public': is_public,
        **_content(obj),
        'others': _public(scenario).exclude(pk=obj.pk)[:3],
        'share_url': request.build_absolute_uri(obj.get_absolute_url()),
    })


def isoseismal_pdf(request, slug, scenario=False):
    from .pdf import build_pdf

    obj, _is_public = _get_visible(request, slug, scenario)
    pdf = build_pdf(obj, _content(obj), request.build_absolute_uri(obj.get_absolute_url()))
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{obj.slug}.pdf"'
    return response
