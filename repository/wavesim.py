"""Wave-propagation simulations (SPECFEM3D) for Gempa Merusak events.

Flow:
  staff  -> POST gempa-merusak/<pk>/simulasi/     queue a WaveSimulation
  worker -> POST /api/wavesim/claim/              take the oldest queued run
  worker -> POST /api/wavesim/<id>/progress/      stage updates
  worker -> POST /api/wavesim/<id>/result/        tar.gz of web assets + result.json
  worker -> POST /api/wavesim/<id>/fail/          error log

The worker runs on the SPECFEM host (172.21.63.51), which can reach this
server but not the other way round, hence the pull model. Worker calls use
a bearer token (WAVESIM_WORKER_TOKEN).
"""
import json
import os
import re
import shutil
import tarfile
from datetime import datetime, time, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from stations.models import Station

from .models import GempaMemusak, WaveSimulation

DEFAULT_PARAMS = {
    'half_width_km': 150,   # block is 300 x 300 km around the epicentre
    'nex': 96,              # ~3 km elements at the surface
    'dt': 0.02,
    'duration_s': 140,
    'frame_every_s': 1.0,
}
STALE_AFTER = timedelta(hours=6)
ASSET_NAME = re.compile(r'^(pgv\.png|frames/f\d{3}\.png)$')
LOG_LIMIT = 20000


def missing_fields(event):
    """Event fields the simulation needs but which are empty."""
    need = ('latitude', 'longitude', 'depth_km', 'magnitude', 'strike', 'dip', 'rake')
    return [f for f in need if getattr(event, f) is None]


def asset_url(sim, name):
    return f'{settings.MEDIA_URL}{sim.asset_dir}/{name}'


def latest_done(event):
    return event.wave_simulations.filter(status=WaveSimulation.STATUS_DONE).first()


def public_context(event):
    """Template context for the result viewer (latest finished run)."""
    sim = latest_done(event)
    if not sim:
        return {}
    r = sim.result or {}
    return {
        'wavesim': sim,
        'wavesim_data': {
            'bounds': r.get('bounds'),
            'frame_times': r.get('frame_times', []),
            'frame_url': asset_url(sim, 'frames/'),
            'pgv_url': asset_url(sim, 'pgv.png'),
            'pgv_scale': r.get('pgv_scale'),
            'seismograms': r.get('seismograms', {}),
            'source': r.get('source'),
            'half_duration_s': r.get('half_duration_s'),
        },
        'wavesim_mesh': r.get('mesh', {}),
    }


# ---------------------------------------------------------------------------
# Staff action
# ---------------------------------------------------------------------------

@login_required
@require_POST
def wavesim_request(request, pk):
    event = get_object_or_404(GempaMemusak, pk=pk)
    missing = missing_fields(event)
    if missing:
        messages.error(request, 'Simulasi butuh data: ' + ', '.join(missing))
    elif event.wave_simulations.filter(status__in=(WaveSimulation.STATUS_QUEUED,
                                                   WaveSimulation.STATUS_RUNNING)).exists():
        messages.info(request, 'Simulasi untuk kejadian ini sudah dalam antrean.')
    else:
        WaveSimulation.objects.create(event=event, params=dict(DEFAULT_PARAMS),
                                      requested_by=request.user)
        messages.success(request, 'Simulasi masuk antrean. Worker di server SPECFEM '
                                  'mengambilnya dalam beberapa menit.')
    return redirect('gempa_merusak_detail', pk=pk)


# ---------------------------------------------------------------------------
# Worker API
# ---------------------------------------------------------------------------

def _authorized(request):
    token = request.headers.get('Authorization', '').removeprefix('Bearer ').strip()
    expected = getattr(settings, 'WAVESIM_WORKER_TOKEN', '')
    return bool(expected) and token == expected


def _worker_api(view):
    def wrapped(request, *args, **kwargs):
        if request.method != 'POST':
            return JsonResponse({'error': 'POST only'}, status=405)
        if not _authorized(request):
            return JsonResponse({'error': 'Unauthorized'}, status=401)
        return view(request, *args, **kwargs)
    return csrf_exempt(wrapped)


def _job_payload(sim):
    e = sim.event
    origin = datetime.combine(e.tanggal, e.origin_time or time(0, 0)) if e.tanggal else None
    stations = [
        {'network': s['network'], 'code': s['code'],
         'latitude': s['latitude'], 'longitude': s['longitude']}
        for s in Station.objects.filter(is_active=True)
        .values('network', 'code', 'latitude', 'longitude').order_by('code')
    ]
    return {
        'id': sim.pk,
        'params': sim.params or DEFAULT_PARAMS,
        'event': {
            'pk': e.pk, 'name': (e.wilayah or f'gm{e.no}')[:30],
            'origin': origin.strftime('%Y-%m-%dT%H:%M:%S') if origin else '1900-01-01T00:00:00',
            'latitude': e.latitude, 'longitude': e.longitude, 'depth_km': e.depth_km,
            'magnitude': e.magnitude, 'strike': e.strike, 'dip': e.dip, 'rake': e.rake,
        },
        'stations': stations,
    }


@_worker_api
def api_claim(request):
    now = timezone.now()
    # A run that has been "running" for hours lost its worker; give up on it.
    WaveSimulation.objects.filter(status=WaveSimulation.STATUS_RUNNING,
                                  started_at__lt=now - STALE_AFTER).update(
        status=WaveSimulation.STATUS_FAILED, finished_at=now,
        log='Worker tidak melapor lebih dari 6 jam.')
    with transaction.atomic():
        sim = (WaveSimulation.objects.select_for_update(skip_locked=True)
               .filter(status=WaveSimulation.STATUS_QUEUED).order_by('requested_at').first())
        if sim is None:
            return JsonResponse({'job': None})
        sim.status = WaveSimulation.STATUS_RUNNING
        sim.stage = 'claimed'
        sim.started_at = now
        sim.save(update_fields=['status', 'stage', 'started_at'])
    return JsonResponse({'job': _job_payload(sim)})


def _running(pk):
    return WaveSimulation.objects.filter(pk=pk, status=WaveSimulation.STATUS_RUNNING).first()


@_worker_api
def api_progress(request, pk):
    sim = _running(pk)
    if sim is None:
        return JsonResponse({'error': 'not running'}, status=409)
    sim.stage = (request.POST.get('stage') or '')[:60]
    sim.save(update_fields=['stage'])
    return JsonResponse({'ok': True})


@_worker_api
def api_fail(request, pk):
    sim = _running(pk)
    if sim is None:
        return JsonResponse({'error': 'not running'}, status=409)
    sim.status = WaveSimulation.STATUS_FAILED
    sim.finished_at = timezone.now()
    sim.log = (request.POST.get('log') or '')[-LOG_LIMIT:]
    sim.save(update_fields=['status', 'finished_at', 'log'])
    return JsonResponse({'ok': True})


def extract_assets(archive, dest):
    """Unpack only the expected PNG files (no paths outside dest, no links)."""
    tmp = dest + '.tmp'
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(os.path.join(tmp, 'frames'))
    n = 0
    with tarfile.open(fileobj=archive, mode='r:gz') as tar:
        for m in tar.getmembers():
            if not (m.isfile() and ASSET_NAME.match(m.name)):
                continue
            with tar.extractfile(m) as src, open(os.path.join(tmp, m.name), 'wb') as out:
                shutil.copyfileobj(src, out)
            n += 1
    shutil.rmtree(dest, ignore_errors=True)
    os.replace(tmp, dest)
    return n


@_worker_api
def api_result(request, pk):
    sim = _running(pk)
    if sim is None:
        return JsonResponse({'error': 'not running'}, status=409)
    upload = request.FILES.get('archive')
    try:
        result = json.loads(request.POST.get('result') or '')
    except ValueError:
        return JsonResponse({'error': 'result must be JSON'}, status=400)
    if upload is None or not isinstance(result, dict):
        return JsonResponse({'error': 'need archive and result'}, status=400)
    try:
        n = extract_assets(upload, os.path.join(settings.MEDIA_ROOT, sim.asset_dir))
    except (tarfile.TarError, OSError) as exc:
        return JsonResponse({'error': f'bad archive: {exc}'}, status=400)
    sim.status = WaveSimulation.STATUS_DONE
    sim.stage = 'done'
    sim.result = result
    sim.log = (request.POST.get('log') or '')[-LOG_LIMIT:]
    sim.finished_at = timezone.now()
    sim.save(update_fields=['status', 'stage', 'result', 'log', 'finished_at'])
    return JsonResponse({'ok': True, 'files': n})
