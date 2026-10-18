"""Cari ShakemapEvent untuk satu kejadian.

event_id ShakemapEvent berupa stempel waktu WIB 14 digit (YYYYMMDDhhmmss). Record lama
(sebelum ±20 April 2026, dari backfill_shakemaps) memakai id XML penuh
"<WIB 14 digit>_<mag>_<lat>_<lon>_<WIB 14 digit>", sehingga pencarian id persis
14 digit tidak menemukannya dan peta intensitasnya tidak tampil.
Origin SeisComP juga bisa berbeda 1–5 detik dari waktu gempa BMKG.
"""
import datetime

from .models import ShakemapEvent

WIB = datetime.timezone(datetime.timedelta(hours=7))
_OFFSETS = (0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5)


def wib_id(dt):
    """Stempel waktu WIB 14 digit dari datetime (aware)."""
    return dt.astimezone(WIB).strftime("%Y%m%d%H%M%S")


def wib_id_to_utc(event_id):
    """datetime UTC dari id WIB 14 digit (atau awalan 14 digit id lama); None bila bukan waktu."""
    try:
        t = datetime.datetime.strptime(event_id[:14], "%Y%m%d%H%M%S")
    except (TypeError, ValueError):
        return None
    return t.replace(tzinfo=WIB).astimezone(datetime.timezone.utc)


def candidate_ids(wib_ts, tolerance=True):
    base = datetime.datetime.strptime(wib_ts, "%Y%m%d%H%M%S")
    offsets = _OFFSETS if tolerance else (0,)
    return [(base + datetime.timedelta(seconds=off)).strftime("%Y%m%d%H%M%S") for off in offsets]


def find_shakemap_event(wib_ts, tolerance=True, prefer_image=True):
    """ShakemapEvent untuk id WIB 14 digit: id persis, lalu id lama berawalan '<id>_',
    mencoba selisih ±5 detik. Record dengan peta intensitas diutamakan."""
    if not wib_ts or len(wib_ts) < 14 or not wib_ts[:14].isdigit():
        return ShakemapEvent.objects.filter(event_id=wib_ts).first() if wib_ts else None
    found = []
    for cand in candidate_ids(wib_ts[:14], tolerance):
        exact = ShakemapEvent.objects.filter(event_id=cand).first()
        if exact:
            found.append(exact)
        found.extend(ShakemapEvent.objects.filter(event_id__startswith=cand + "_"))
        if found and (not prefer_image or any(s.shakemap_image for s in found)):
            break
    if prefer_image:
        with_image = [s for s in found if s.shakemap_image]
        if with_image:
            return with_image[0]
    return found[0] if found else None


def shakemap_index():
    """{id WIB 14 digit: ShakemapEvent} untuk semua record (format baru & lama), untuk proses massal.
    Bila satu id punya beberapa record, yang memiliki peta intensitas diutamakan."""
    index = {}
    for s in ShakemapEvent.objects.all():
        key = s.event_id[:14]
        if not key.isdigit():
            continue
        if key not in index or (s.shakemap_image and not index[key].shakemap_image):
            index[key] = s
    return index
