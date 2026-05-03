from django.http import JsonResponse
from .models import Station, StationStatus


def api_stations(request):
    stations = Station.objects.filter(is_active=True).select_related('status')
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
