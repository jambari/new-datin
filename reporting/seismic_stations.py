"""Status kesehatan stasiun seismik terkini untuk peta dan lampiran laporan.

Sumber: hasil Station Health Monitoring harian (qc_review.StationDailyQC/StationDiagnosis, hari
data terakhir) dan daftar stasiun seismograf (stations.Station) untuk stasiun yang tidak lagi
mengirim data. Koordinat dari stations.Station atau StationResult (inventaris SeisComP).
"""
from collections import defaultdict

from django.db.models import Max

from qc_review import station_rules
from qc_review.models import StationDailyQC, StationDiagnosis, StationResult
from stations.models import Station

STATES = {
    "baik": ("Baik", "#16a34a"),
    "gangguan": ("Gangguan", "#facc15"),
    "off": ("Off / tidak ada data", "#111827"),
}


def _coords():
    out = {}
    for net, sta, lat, lon in (StationResult.objects.exclude(station_lat=None).exclude(station_lon=None)
                               .values_list("network", "station", "station_lat", "station_lon")
                               .order_by("network", "station", "-id").distinct("network", "station")):
        out[(net, sta)] = (lat, lon)
    for s in Station.objects.filter(station_type=Station.TYPE_SEISMIC):
        out[(s.network, s.code)] = (s.latitude, s.longitude)
    return out


def station_health():
    """Status tiap stasiun pada hari data terakhir: baik (hijau), gangguan (kuning), off (hitam)."""
    day = StationDailyQC.objects.aggregate(d=Max("day"))["d"]
    if day is None:
        return None
    sev = defaultdict(list)
    for net, sta, status in StationDailyQC.objects.filter(day=day).values_list("network", "station", "status"):
        sev[(net, sta)].append(status)
    channels = defaultdict(set)
    no_data = defaultdict(set)
    notes = defaultdict(list)
    for d in StationDiagnosis.objects.filter(day=day, severity__in=("red", "yellow")).order_by("channel"):
        key = (d.network, d.station)
        if d.code == "NO_DATA":
            no_data[key].add(d.channel)
        elif d.message_id not in notes[key]:
            notes[key].append(d.message_id)
    for net, sta, cha in StationDailyQC.objects.filter(day=day).values_list("network", "station", "channel"):
        channels[(net, sta)].add(cha)
    coords = _coords()
    stations = []
    for key, sevs in sev.items():
        if channels[key] and channels[key] <= no_data[key]:
            state = "off"
        else:
            state = "baik" if station_rules.worst(sevs) == "green" else "gangguan"
        if no_data[key] and state != "off":
            notes[key].insert(0, f"Tidak ada data pada kanal {', '.join(sorted(no_data[key]))}.")
        stations.append({"network": key[0], "station": key[1], "state": state, "notes": notes[key]})
    # Seismograf terdaftar yang tidak lagi mengirim data ke arsip tidak muncul di QC harian.
    for s in Station.objects.filter(station_type=Station.TYPE_SEISMIC, is_active=True):
        if (s.network, s.code) not in sev:
            stations.append({"network": s.network, "station": s.code, "state": "off",
                             "notes": ["Tidak ada data di arsip waveform."]})
    for s in stations:
        s["lat"], s["lon"] = coords.get((s["network"], s["station"]), (None, None))
        s["label"], s["color"] = STATES[s["state"]]
    stations.sort(key=lambda s: (list(STATES).index(s["state"]), s["network"], s["station"]))
    counts = [(STATES[k][0], STATES[k][1], sum(1 for s in stations if s["state"] == k)) for k in STATES]
    return {"day": day, "stations": stations, "counts": counts, "n": len(stations),
            "problems": [s for s in stations if s["state"] != "baik"]}
