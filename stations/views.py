import json
from datetime import datetime, timezone
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import Station, StationStatus, StationAvailabilitySample
from .constants import ACCELEROGRAPH_STATIONS, SEISMIC_STATIONS


def api_stations(request):
    qs = Station.objects.filter(is_active=True)
    stype = request.GET.get('type')          # 'seismic' | 'accelero' | omit for all
    if stype == 'accelero':
        qs = qs.filter(code__in=ACCELEROGRAPH_STATIONS)
    elif stype == 'seismic':
        qs = qs.filter(code__in=SEISMIC_STATIONS)
    stations = qs.select_related('status')
    data = []
    for station in stations:
        try:
            st = station.status
            status = st.status
            latency = st.latency
            last_packet = st.last_packet_time.isoformat() if st.last_packet_time else None
            last_updated = st.last_updated.isoformat() if st.last_updated else None
            channel_info = st.channel_info
        except StationStatus.DoesNotExist:
            status = 'off'
            latency = None
            last_packet = None
            last_updated = None
            channel_info = ''

        if latency is not None:
            if latency < 60:
                latency_str = f"{latency:.1f} s"
            elif latency < 3600:
                latency_str = f"{latency / 60:.1f} min"
            else:
                latency_str = f"{latency / 3600:.1f} jam"
        else:
            latency_str = "N/A"

        data.append({
            'network': station.network,
            'code': station.code,
            'name': station.name,
            'latitude': station.latitude,
            'longitude': station.longitude,
            'kota': station.kota,
            'provinsi': station.provinsi,
            'sensor': station.sensor,
            'digitizer': station.digitizer,
            'channel': channel_info or station.channel,
            'status': status,
            'latency': latency,
            'latency_str': latency_str,
            'last_packet': last_packet,
            'last_updated': last_updated,
        })

    return JsonResponse({'stations': data, 'count': len(data)})


@csrf_exempt
@require_POST
def api_push_seismic_status(request):
    """
    Receive seismic station status pushed from the SeisComP acquisition server.
    POST /api/stations/push-seismic/
    Header: Authorization: Token <SEISMIC_STATUS_TOKEN>
    Body (JSON):
      {"stations": [{"network":"IA","code":"JAY","channel":"BHZ",
                     "latency":45.2,"last_packet":"2026-05-08T10:30:00Z"}, ...]}
    """
    token = getattr(settings, 'SEISMIC_STATUS_TOKEN', '')
    auth  = request.headers.get('Authorization', '')
    if not token or auth != f'Token {token}':
        return JsonResponse({'error': 'unauthorized'}, status=401)

    try:
        payload = json.loads(request.body)
        stations_data = payload.get('stations', [])
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({'error': 'invalid JSON'}, status=400)

    updated = skipped = 0
    now = datetime.now(timezone.utc)

    for item in stations_data:
        try:
            station = Station.objects.get(
                network=item['network'], code=item['code'], station_type='seismic'
            )
        except Station.DoesNotExist:
            skipped += 1
            continue

        latency = item.get('latency')
        status  = StationStatus.compute_status(latency)

        last_packet = None
        lp_str = item.get('last_packet')
        if lp_str:
            try:
                last_packet = datetime.fromisoformat(lp_str.replace('Z', '+00:00'))
            except ValueError:
                pass

        obj, _ = StationStatus.objects.get_or_create(station=station)
        obj.status          = status
        obj.latency         = latency
        obj.last_packet_time = last_packet
        obj.channel_info    = item.get('channel', '')
        obj.save()

        StationAvailabilitySample.objects.create(
            station=station, sampled_at=now, status=status
        )
        updated += 1

    return JsonResponse({'updated': updated, 'skipped': skipped})
