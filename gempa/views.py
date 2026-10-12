"""View katalog gempa yang diport dari views.py .188.

- `latest_event_notify`: dipanggil berkala oleh static/js/gempa_notify.js.
- `laporan_bulanan`, `gempa_susulan` (+ `focal_save`, `focal_position_save`):
  halaman yang dibuka dari tombol "Laporan Bulanan" / "Gempa Susulan" di
  changelist katalog (admin/gempa/change_list.html).

Bedanya dengan .188: data integrasi & gempa dirasakan diambil langsung dari
aplikasi repository (di .188 lewat HTTPS ke API .189 ini), dan halaman hanya
untuk staf yang sudah login ke /gempa-admin/.
"""
import calendar
import json
import urllib.parse
import urllib.request
from datetime import date

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from repository.views import dirasakan_events, laporan_bulanan_events

from .apps import OPERATOR_GROUPS, landing_url_name_for
from .models import (Gempa, Balaigempa, Gempasorong, Gempanabire,
                     Satudatagempa, Significant, City, FocalMechanism,
                     haversine_km, cardinal_direction)

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


# Grup operator katalog (dibuat/dirapikan oleh post_migrate, lihat gempa/apps.py).
CATALOG_GROUP_NAMES = frozenset(OPERATOR_GROUPS)


def post_login_redirect(request):
    """Tujuan setelah login tanpa parameter ?next=.

    Operator katalog diarahkan ke katalog kantornya sendiri, misalnya
    angkasa@bmkg.go.id -> /gempa-admin/gempa/gempa/ (lihat OPERATOR_GROUPS
    di gempa/apps.py). Semua user lain tetap ke halaman biasa
    (POST_LOGIN_REDIRECT_URL, default /dashboard/).

    Superuser tidak dialihkan: mereka memakai situs utama seperti biasa.
    """
    if not request.user.is_authenticated:
        return redirect(settings.LOGIN_URL)

    group_names = set(request.user.groups.values_list('name', flat=True))
    if not request.user.is_superuser:
        landing = landing_url_name_for(group_names)
        if landing:
            return redirect(landing)

    return redirect(settings.POST_LOGIN_REDIRECT_URL)


# ── Laporan Bulanan & Gempa Susulan (port .188) ─────────────────────────────

BULAN_NAMES = ["", "JANUARI", "FEBRUARI", "MARET", "APRIL", "MEI", "JUNI",
               "JULI", "AGUSTUS", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DESEMBER"]

UPT_BY_USERNAME = {
    'pgr5':   'PUSAT GEMPABUMI REGIONAL V',
    'sorong':  'STASIUN GEOFISIKA SORONG',
    'nabire':  'STASIUN GEOFISIKA NABIRE',
}

# Halaman ini dibuka dari changelist /gempa-admin/; user yang belum login
# diarahkan ke halaman login katalog (bukan login OTP situs utama).
catalog_staff_required = staff_member_required(login_url=reverse_lazy('gempa_admin:login'))


@catalog_staff_required
@require_POST
def focal_save(request):
    """Simpan focal mechanism manual (strike, dip, rake) untuk gempa utama."""
    source = request.POST.get("source", "JAY")
    event_pk = request.POST.get("event_pk", "")
    next_url = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()},
                                           require_https=request.is_secure()):
        next_url = reverse("gempa:gempa-susulan")
    try:
        event_pk_int = int(event_pk)
        strike_f = float(request.POST.get("strike", ""))
        dip_f = float(request.POST.get("dip", ""))
        rake_f = float(request.POST.get("rake", ""))
    except (TypeError, ValueError):
        return redirect(next_url)
    if not (0 <= strike_f <= 360 and 0 <= dip_f <= 90 and -180 <= rake_f <= 180):
        return redirect(next_url)

    label = ""
    model_map = {"JAY": Gempa, "NBPI": Gempanabire, "PGR5": Balaigempa, "SWI": Gempasorong}
    model = model_map.get(source)
    if model is not None:
        try:
            ev = model.objects.filter(pk=event_pk_int).first()
            if ev is not None:
                label = "{} {}".format(ev.tanggal, str(ev.origin)[:8])
        except Exception:
            pass

    FocalMechanism.objects.update_or_create(
        source=source,
        event_pk=event_pk_int,
        defaults={
            "strike": strike_f,
            "dip": dip_f,
            "rake": rake_f,
            "is_auto": False,
            "origin_label": label,
        },
    )
    return redirect(next_url)


@catalog_staff_required
@require_POST
def focal_position_save(request):
    """Simpan posisi (offset) beach ball hasil drag user di peta."""
    source = request.POST.get("source", "JAY")
    event_pk = request.POST.get("event_pk", "")
    try:
        event_pk_int = int(event_pk)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False}, status=400)
    fm = FocalMechanism.objects.filter(source=source, event_pk=event_pk_int).first()
    if fm is None:
        return JsonResponse({"ok": False}, status=404)
    offset_lat_raw = (request.POST.get("offset_lat") or "").strip()
    offset_lon_raw = (request.POST.get("offset_lon") or "").strip()
    if offset_lat_raw == "" or offset_lon_raw == "":
        fm.offset_lat = None
        fm.offset_lon = None
    else:
        try:
            fm.offset_lat = float(offset_lat_raw)
            fm.offset_lon = float(offset_lon_raw)
        except ValueError:
            return JsonResponse({"ok": False}, status=400)
    fm.save(update_fields=["offset_lat", "offset_lon", "updated_at"])
    return JsonResponse({"ok": True})


def _get_upt(user):
    if hasattr(user, 'is_authenticated') and user.is_authenticated:
        uname = getattr(user, 'username', '').lower()
        if uname in UPT_BY_USERNAME:
            return UPT_BY_USERNAME[uname]
        # fallback: check group membership
        groups = set(user.groups.values_list('name', flat=True))
        for key, name in UPT_BY_USERNAME.items():
            if key in groups:
                return name
    return 'STASIUN GEOFISIKA JAYAPURA'


_CITIES_CACHE = None

def _get_cities():
    global _CITIES_CACHE
    if _CITIES_CACHE is None:
        _CITIES_CACHE = list(City.objects.all())
    return _CITIES_CACHE

def _nearest_ket(lat, lon):
    cities = _get_cities()
    if not cities:
        return ''
    nearest = min(cities, key=lambda c: haversine_km(lat, lon, float(c.latitude), float(c.longitude)))
    dist = round(haversine_km(lat, lon, float(nearest.latitude), float(nearest.longitude)))
    arah = cardinal_direction(lat, lon, float(nearest.latitude), float(nearest.longitude))
    return f"{dist} km {arah} {nearest.name}"


# Di .188 dua fungsi ini memanggil API HTTPS .189
# (/api/gempa/laporan-bulanan/ dan /api/gempa/dirasakan/). Di sini datanya
# satu database, jadi helper repository dipanggil langsung.
def _fetch_integrasi(year, month):
    return laporan_bulanan_events(year, month)

def _fetch_dirasakan(request, year, month):
    return dirasakan_events(year, month, request.build_absolute_uri)


def _source_stats(events):
    mags   = [e['mag']   for e in events]
    depths = [e['depth'] for e in events]
    return {
        'total':       len(events),
        'max_mag':     round(max(mags),   1) if mags   else 0,
        'min_mag':     round(min(mags),   1) if mags   else 0,
        'mag_lt3':     sum(1 for m in mags if m < 3),
        'mag_35':      sum(1 for m in mags if 3 <= m < 5),
        'mag_gte5':    sum(1 for m in mags if m >= 5),
        'dep_shallow': sum(1 for d in depths if d < 60),
        'dep_mid':     sum(1 for d in depths if 60 <= d < 300),
        'dep_deep':    sum(1 for d in depths if d >= 300),
        'felt':        sum(1 for e in events if e.get('terasa')),
    }


@catalog_staff_required
def laporan_bulanan(request, template_name="gempa/laporan_bulanan.html"):
    today = date.today()
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    try:
        date.fromisoformat(date_from)
        date.fromisoformat(date_to)
    except ValueError:
        # Tanggal kosong/rusak (mis. URL diketik manual): pakai year/month.
        date_from = date_to = ""

    if not date_from or not date_to:
        try:
            year  = int(request.GET.get("year",  today.year))
            month = int(request.GET.get("month", today.month))
            if not (1 <= month <= 12):
                month = today.month
        except (ValueError, TypeError):
            year, month = today.year, today.month
        _, num_days = calendar.monthrange(year, month)
        date_from = "{:04d}-{:02d}-01".format(year, month)
        date_to = "{:04d}-{:02d}-{:02d}".format(year, month, num_days)

    from datetime import timedelta
    from datetime import date as dt_date
    from_f = dt_date.fromisoformat(date_from) if date_from else today.replace(day=1)
    to_f = dt_date.fromisoformat(date_to) if date_to else today
    end_date = to_f + timedelta(days=1)

    source = request.GET.get("source", "PGR5")
    try:
        from_dt = dt_date.fromisoformat(date_from)
        to_dt = dt_date.fromisoformat(date_to)
        if from_dt.month == to_dt.month and from_dt.year == to_dt.year:
            formatted_bulan = BULAN_NAMES[from_dt.month] + ' ' + str(from_dt.year)
        else:
            formatted_bulan = BULAN_NAMES[from_dt.month] + '-' + BULAN_NAMES[to_dt.month] + ' ' + str(to_dt.year)
    except Exception:
        formatted_bulan = "{} s.d {}".format(date_from, date_to)

    if source in ("JAY", "NBPI", "PGR5", "SWI"):
        source_map = {
            "JAY": Gempa,
            "NBPI": Gempanabire,
            "PGR5": Balaigempa,
            "SWI": Gempasorong,
        }
        model = source_map[source]
        qs = model.objects.filter(tanggal__gte=from_f, tanggal__lt=end_date).values(
            "event_id","tanggal","origin","lintang","bujur","magnitudo","depth","ket")
        all_events = []
        for e in qs:
            try:
                ot = str(e["origin"])[:8]
                lat_str = str(e["lintang"]).replace("\xb0","").strip()
                neg = -1 if "LS" in lat_str else 1
                lat_val = float(lat_str.replace("LU","").replace("LS","").strip()) * neg
                all_events.append({
                    "event_id": e["event_id"] or "",
                    "tanggal": str(e["tanggal"]),
                    "origin": ot,
                    "lat": lat_val,
                    "lon": float(str(e["bujur"])),
                    "mag": float(e["magnitudo"]) if e["magnitudo"] else 0,
                    "depth": int(e["depth"]) if e["depth"] else 0,
                    "ket": e["ket"] or "",
                    "terasa": False,
                    "source": source,
                })
            except:
                pass
    else:
        all_events = [e for e in _fetch_integrasi(from_f.year, from_f.month) if e.get("depth", 0) != 0]

    dirasakan_events = [e for e in _fetch_dirasakan(request, from_f.year, from_f.month) if e.get("depth", 0) != 0]

    for ev in all_events:
        try:
            if not ev.get("ket"):
                ev["ket"] = _nearest_ket(ev["lat"], ev["lon"])
        except Exception:
            pass

    stats = {
        "Integrasi": _source_stats(all_events),
        "all":       _source_stats(all_events),
    }

    year_range  = range(max(2020, today.year - 5), today.year + 1)
    upt_name    = _get_upt(request.user)
    felt_count  = len(dirasakan_events)

    return render(request, template_name, {
        "date_from":       date_from,
        "date_to":         date_to,
        "source":          source,
        "formatted_bulan": formatted_bulan,
        "num_days":        0,
        "all_events":      json.dumps(all_events),
        "stats":           stats,
        "year_range":      year_range,
        "month_names":     BULAN_NAMES[1:],
        "current_month":   0,
        "current_year":    0,
        "upt_name":          upt_name,
        "felt_count":        felt_count,
        "dirasakan_events":  json.dumps(dirasakan_events),
    })


_USGS_MISS_CACHE = {}


def _usgs_focal_mechanism(origin_dt, lat, lon, mag):
    """Ambil focal mechanism (strike, dip, rake) dari USGS FDSN event API.

    Mencari event USGS dalam jendela ±75 detik dan radius 120 km dari origin,
    lalu mengambil nodal-plane-1 dari produk moment-tensor terdekat.
    Return None jika tidak ditemukan/gagal.
    """
    import time as _time
    import datetime as _dtmod
    from datetime import timedelta, timezone

    _key = "{}|{:.2f}|{:.2f}".format(origin_dt.strftime("%Y%m%d%H%M%S"), float(lat), float(lon))

    def _miss():
        _USGS_MISS_CACHE[_key] = _time.time()
        return None

    _cached = _USGS_MISS_CACHE.get(_key)
    if _cached and (_time.time() - _cached) < 86400:
        return _miss()

    try:
        start = (origin_dt - timedelta(seconds=75)).strftime("%Y-%m-%dT%H:%M:%S")
        end   = (origin_dt + timedelta(seconds=75)).strftime("%Y-%m-%dT%H:%M:%S")
        params = urllib.parse.urlencode({
            "format": "geojson",
            "starttime": start,
            "endtime": end,
            "latitude": round(float(lat), 4),
            "longitude": round(float(lon), 4),
            "maxradiuskm": 120,
            "minmagnitude": max(4.0, round(float(mag) - 0.6, 1)),
            "orderby": "time",
        })
        url = "https://earthquake.usgs.gov/fdsnws/event/1/query?" + params
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        features = data.get("features", []) or []
        # Summary GeoJSON tidak memuat produk moment-tensor; cari eventid
        # terdekat lalu ambil detail-nya (endpoint eventid mengembalikan
        # Feature lengkap beserta products.moment-tensor).
        best_eid = None
        best_dt = None
        for feat in features:
            props = feat.get("properties", {}) or {}
            t_ms = props.get("time")
            if t_ms is None:
                continue
            ev_dt = _dtmod.datetime.fromtimestamp(t_ms / 1000.0, timezone.utc).replace(tzinfo=None)
            if best_dt is None or abs((ev_dt - origin_dt).total_seconds()) < abs((best_dt - origin_dt).total_seconds()):
                best_dt = ev_dt
                best_eid = feat.get("id")
                if not best_eid:
                    ids = (props.get("ids") or "").replace(",", " ").split()
                    best_eid = ids[0] if ids else None
        if not best_eid:
            return _miss()

        detail_url = ("https://earthquake.usgs.gov/fdsnws/event/1/query"
                      "?eventid={}&format=geojson").format(urllib.parse.quote(best_eid))
        with urllib.request.urlopen(detail_url, timeout=10) as resp:
            detail = json.loads(resp.read().decode("utf-8"))
        # Respons detail: bisa FeatureCollection atau Feature tunggal.
        dprops = None
        if isinstance(detail, dict):
            feats = detail.get("features")
            if isinstance(feats, list) and feats:
                dprops = feats[0].get("properties", {}) or {}
            elif detail.get("properties") is not None:
                dprops = detail.get("properties", {}) or {}
        if dprops is None:
            return _miss()
        mt_products = (dprops.get("products") or {}).get("moment-tensor", []) or []
        if not mt_products:
            return _miss()
        best_props = mt_products[0].get("properties", {}) or {}
        # USGS memakai dua format: objek "nodal-plane-1" (nested) atau
        # kunci datar "nodal-plane-1-strike/dip/rake".
        np1 = best_props.get("nodal-plane-1") or {}
        strike = np1.get("strike")
        dip = np1.get("dip")
        rake = np1.get("rake")
        if strike is None:
            strike = best_props.get("nodal-plane-1-strike")
        if dip is None:
            dip = best_props.get("nodal-plane-1-dip")
        if rake is None:
            rake = best_props.get("nodal-plane-1-rake")
        if strike is None or dip is None or rake is None:
            return _miss()
        return {
            "strike": float(strike),
            "dip": float(dip),
            "rake": float(rake),
            "magnitude": float(best_props.get("derived-magnitude") or best_props.get("magnitude") or mag),
            "depth": float(best_props.get("depth") or best_props.get("derived-depth") or 0),
        }
    except Exception:
        return _miss()


@catalog_staff_required
def gempa_susulan(request):
    from datetime import datetime as dt_datetime, timedelta

    today = date.today()
    source = request.GET.get("source", "JAY")
    source_map = {
        "JAY": Gempa,
        "NBPI": Gempanabire,
        "PGR5": Balaigempa,
        "SWI": Gempasorong,
    }
    model = source_map.get(source, Gempa)

    main_qs = model.objects.filter(magnitudo__gt=4.5).order_by("-tanggal", "-origin")

    def _fmt_label(e):
        return "{} {} UTC - M{} - {}".format(
            str(e.tanggal), str(e.origin)[:8], str(e.magnitudo), (e.ket or "")[:60])

    main_events = [
        {"pk": e.pk, "label": _fmt_label(e)}
        for e in main_qs[:500]
    ]

    selected_pk = request.GET.get("event_pk", "")
    mainshock = None
    if selected_pk:
        try:
            mainshock = model.objects.filter(pk=int(selected_pk)).first()
        except (ValueError, TypeError):
            mainshock = None
    if mainshock is None and main_events:
        try:
            mainshock = model.objects.filter(pk=int(main_events[0]["pk"])).first()
        except (ValueError, TypeError):
            mainshock = None
    if mainshock is None:
        mainshock = model.objects.order_by("-tanggal", "-origin").first()

    if mainshock is not None:
        origin_str = str(mainshock.origin)[:8]
        try:
            start_dt = dt_datetime.strptime(
                "{} {}".format(mainshock.tanggal, origin_str), "%Y-%m-%d %H:%M:%S")
        except Exception:
            start_dt = dt_datetime.combine(mainshock.tanggal, dt_datetime.min.time())
        selected_pk = str(mainshock.pk)
    else:
        start_dt = dt_datetime.combine(today, dt_datetime.min.time())
        selected_pk = ""

    date_to_raw = request.GET.get("date_to", "").strip()
    end_dt = None
    if date_to_raw:
        date_to_raw = date_to_raw.replace("T", " ").strip()
        if len(date_to_raw) == 16:
            date_to_raw += ":00"
        try:
            end_dt = dt_datetime.strptime(date_to_raw, "%Y-%m-%d %H:%M:%S")
        except Exception:
            end_dt = None

    if end_dt is None or end_dt < start_dt:
        if start_dt.month == 12:
            next_month = start_dt.replace(year=start_dt.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            next_month = start_dt.replace(month=start_dt.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end_dt = next_month - timedelta(seconds=1)

    date_to_widget = end_dt.strftime("%Y-%m-%dT%H:%M")

    qs = model.objects.filter(tanggal__gte=start_dt.date(), tanggal__lte=end_dt.date())
    all_events = []
    for e in qs:
        try:
            ot = str(e.origin)[:8]
            dt = dt_datetime.strptime("{} {}".format(e.tanggal, ot), "%Y-%m-%d %H:%M:%S")
            if dt < start_dt or dt > end_dt:
                continue
            lat_str = str(e.lintang).replace("\xb0", "").strip()
            neg = -1 if "LS" in lat_str else 1
            lat_val = float(lat_str.replace("LU", "").replace("LS", "").strip()) * neg
            all_events.append({
                "event_id": e.event_id or "",
                "tanggal": str(e.tanggal),
                "origin": ot,
                "lat": lat_val,
                "lon": float(str(e.bujur)),
                "mag": float(e.magnitudo) if e.magnitudo else 0,
                "depth": int(e.depth) if e.depth else 0,
                "ket": e.ket or "",
                "terasa": bool(getattr(e, "terasa", False)),
                "source": source,
            })
        except Exception:
            pass

    for ev in all_events:
        try:
            if not ev.get("ket"):
                ev["ket"] = _nearest_ket(ev["lat"], ev["lon"])
        except Exception:
            pass

    dirasakan_events = []
    ym = set()
    cur = start_dt
    while cur <= end_dt and len(ym) < 24:
        ym.add((cur.year, cur.month))
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)
    for year, month in sorted(ym):
        for ev in _fetch_dirasakan(request, year, month):
            try:
                if not ev.get("lat") or not ev.get("lon") or ev.get("depth", 0) == 0:
                    continue
                ot = str(ev.get("origin", ""))[:8]
                dt = dt_datetime.strptime("{} {}".format(ev.get("tanggal"), ot), "%Y-%m-%d %H:%M:%S")
                if start_dt <= dt <= end_dt:
                    dirasakan_events.append(ev)
            except Exception:
                continue

    mainshock_location = ""
    mainshock_mag_label = ""
    mainshock_date_indo = ""
    if mainshock is not None:
        try:
            m_lat_str = str(mainshock.lintang).replace("\xb0", "").strip()
            m_neg = -1 if "LS" in m_lat_str else 1
            m_lat = float(m_lat_str.replace("LU", "").replace("LS", "").strip()) * m_neg
            m_lon = float(str(mainshock.bujur))
            cities = _get_cities()
            if cities:
                nearest = min(cities, key=lambda c: haversine_km(m_lat, m_lon, float(c.latitude), float(c.longitude)))
                mainshock_location = nearest.name
        except Exception:
            mainshock_location = ""
        try:
            mainshock_mag_label = str(mainshock.magnitudo).replace(".", ",")
        except Exception:
            mainshock_mag_label = ""
        try:
            mainshock_date_indo = "{:02d} {} {}".format(
                mainshock.tanggal.day, BULAN_NAMES[mainshock.tanggal.month].capitalize(), mainshock.tanggal.year)
        except Exception:
            mainshock_date_indo = ""

    mainshock_lat = None
    mainshock_lon = None
    origin_dt = None
    if mainshock is not None:
        try:
            m_lat_str = str(mainshock.lintang).replace("\xb0", "").strip()
            m_neg = -1 if "LS" in m_lat_str else 1
            mainshock_lat = float(m_lat_str.replace("LU", "").replace("LS", "").strip()) * m_neg
            mainshock_lon = float(str(mainshock.bujur))
        except Exception:
            mainshock_lat = None
            mainshock_lon = None
        try:
            origin_dt = dt_datetime.strptime(
                "{} {}".format(mainshock.tanggal, str(mainshock.origin)[:8]), "%Y-%m-%d %H:%M:%S")
        except Exception:
            origin_dt = None

    focal = None
    if mainshock is not None:
        focal = FocalMechanism.objects.filter(source=source, event_pk=mainshock.pk).first()
        if focal is None and origin_dt is not None and mainshock_lat is not None and mainshock_lon is not None:
            fetched = _usgs_focal_mechanism(origin_dt, mainshock_lat, mainshock_lon, float(mainshock.magnitudo or 0))
            if fetched is not None:
                try:
                    focal = FocalMechanism.objects.create(
                        source=source,
                        event_pk=mainshock.pk,
                        strike=fetched["strike"],
                        dip=fetched["dip"],
                        rake=fetched["rake"],
                        magnitude=fetched.get("magnitude"),
                        depth=fetched.get("depth"),
                        is_auto=True,
                        origin_label="{} {}".format(mainshock.tanggal, str(mainshock.origin)[:8]),
                    )
                except Exception:
                    focal = FocalMechanism.objects.filter(source=source, event_pk=mainshock.pk).first()

    focal_json = json.dumps({
        "strike": focal.strike,
        "dip": focal.dip,
        "rake": focal.rake,
        "is_auto": bool(focal.is_auto),
        "source_label": "USGS FDSN (auto)" if focal.is_auto else "Manual",
        "offset_lat": focal.offset_lat,
        "offset_lon": focal.offset_lon,
    } if focal is not None else None)

    polygon_raw = request.GET.get("polygon", "")
    polygon_coords = []
    if polygon_raw:
        try:
            parsed = json.loads(polygon_raw)
            if isinstance(parsed, list):
                for p in parsed:
                    if isinstance(p, (list, tuple)) and len(p) >= 2:
                        polygon_coords.append([float(p[0]), float(p[1])])
        except Exception:
            polygon_coords = []

    if len(polygon_coords) >= 3:
        def _point_in_polygon(lat, lon, poly):
            inside = False
            j = len(poly) - 1
            for i in range(len(poly)):
                lat_i, lon_i = poly[i][0], poly[i][1]
                lat_j, lon_j = poly[j][0], poly[j][1]
                if ((lat_i > lat) != (lat_j > lat)) and (lon < (lon_j - lon_i) * (lat - lat_i) / ((lat_j - lat_i) or 1e-12) + lon_i):
                    inside = not inside
                j = i
            return inside

        all_events = [e for e in all_events if _point_in_polygon(e["lat"], e["lon"], polygon_coords)]
        dirasakan_events = [e for e in dirasakan_events if _point_in_polygon(float(e["lat"]), float(e["lon"]), polygon_coords)]

    # Jumlah dirasakan: cek kolom terasa/dirasakan pada model sumber,
    # fallback ke API dirasakan (36.91.166.189) jika model tidak punya data dirasakan.
    model_felt = sum(1 for e in all_events if e.get("terasa"))
    felt_count = model_felt if model_felt > 0 else len(dirasakan_events)

    stats = {"Integrasi": _source_stats(all_events), "all": _source_stats(all_events)}

    if start_dt.month == end_dt.month and start_dt.year == end_dt.year:
        formatted_bulan = BULAN_NAMES[start_dt.month] + " " + str(start_dt.year)
    else:
        formatted_bulan = BULAN_NAMES[start_dt.month] + "-" + BULAN_NAMES[end_dt.month] + " " + str(end_dt.year)

    try:
        period_end_label = "{:02d} {} {} {:02d}:{:02d}:{:02d}".format(
            end_dt.day, BULAN_NAMES[end_dt.month].capitalize(), end_dt.year,
            end_dt.hour, end_dt.minute, end_dt.second)
    except Exception:
        period_end_label = date_to_widget

    return render(request, "gempa/gempa_susulan.html", {
        "date_from": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "date_to": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "date_to_widget": date_to_widget,
        "source": source,
        "formatted_bulan": formatted_bulan,
        "main_events": main_events,
        "selected_event_pk": selected_pk,
        "all_events": json.dumps(all_events),
        "stats": stats,
        "year_range": range(max(2020, today.year - 5), today.year + 1),
        "month_names": BULAN_NAMES[1:],
        "current_month": 0,
        "current_year": 0,
        "upt_name": _get_upt(request.user),
        "felt_count": felt_count,
        "dirasakan_events": json.dumps(dirasakan_events),
        "mainshock_location": mainshock_location,
        "mainshock_mag_label": mainshock_mag_label,
        "mainshock_date_indo": mainshock_date_indo,
        "period_end_label": period_end_label,
        "mainshock_lat": json.dumps(mainshock_lat),
        "mainshock_lon": json.dumps(mainshock_lon),
        "focal_json": focal_json,
        "polygon_json": json.dumps(polygon_coords),
        "polygon_count": len(polygon_coords),
    })
