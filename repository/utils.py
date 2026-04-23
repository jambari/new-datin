import math


def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bearing_to_direction(bearing):
    dirs = ['Utara', 'TimurLaut', 'Timur', 'Tenggara', 'Selatan', 'BaratDaya', 'Barat', 'BaratLaut']
    return dirs[round(bearing / 45) % 8]


def calculate_remark(lat, lon):
    from .models import ReferenceLocation
    locations = list(ReferenceLocation.objects.all())
    if not locations:
        return ""

    nearest = min(locations, key=lambda loc: haversine(lat, lon, loc.latitude, loc.longitude))
    distance = round(haversine(lat, lon, nearest.latitude, nearest.longitude))

    lat1, lon1 = math.radians(lat), math.radians(lon)
    lat2, lon2 = math.radians(nearest.latitude), math.radians(nearest.longitude)
    x = math.sin(lon2 - lon1) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    bearing = (math.degrees(math.atan2(x, y)) + 360) % 360

    direction = bearing_to_direction(bearing)
    city_display = nearest.name.title()
    return f"{distance} Km {direction} {city_display}"
