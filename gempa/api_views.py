from datetime import datetime, time
from django.http import JsonResponse
from .models import Gempa, Balaigempa, Gempanabire, Gempasorong


LIMIT = 30


def _iso_utc(tanggal, origin):
    if tanggal is None:
        return None
    if isinstance(origin, time):
        hh, mm, ss = origin.hour, origin.minute, origin.second
    else:
        s = str(origin or '00:00:00')[:8]
        try:
            t = datetime.strptime(s, '%H:%M:%S').time()
            hh, mm, ss = t.hour, t.minute, t.second
        except ValueError:
            hh = mm = ss = 0
    return f"{tanggal.isoformat()}T{hh:02d}:{mm:02d}:{ss:02d}Z"


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _feature_collection(qs):
    features = []
    for o in qs:
        if not o.event_id:
            continue
        lon = _to_float(o.bujur)
        lat = _to_float(o.lintang)
        if lon is None or lat is None:
            continue
        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
            'properties': {
                'id': o.event_id,
                'time': _iso_utc(o.tanggal, o.origin),
                'mag': _to_float(o.magnitudo),
                'depth': o.depth,
                'place': (getattr(o, 'ket', '') or ''),
                'status': 'M',
                'fase': 0,
            },
        })
    return JsonResponse({'type': 'FeatureCollection', 'features': features})


def _latest(model):
    return model.objects.exclude(event_id__isnull=True).exclude(event_id='').order_by('-tanggal', '-origin')[:LIMIT]


def angkasa_for_shakemap(request):
    return _feature_collection(_latest(Gempa))


def earthquakes(request):
    return _feature_collection(_latest(Balaigempa))


def nabire_for_shakemap(request):
    return _feature_collection(_latest(Gempanabire))


def sorong_for_shakemap(request):
    return _feature_collection(_latest(Gempasorong))
