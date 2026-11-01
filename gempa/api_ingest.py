"""API ingest event SeisComp (pengganti insertgempa.php di .188)."""
import re
import hmac
import logging
from datetime import timedelta

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .seiscomp import INGEST_REGIONS, STAGE_SEND, SeiscompError, ingest

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r'^Bearer\s+(?P<token>.+)$', re.IGNORECASE)


def _bearer_token(request) -> str:
    header = request.headers.get('Authorization', '') or ''
    match = _TOKEN_RE.match(header.strip())
    return (match.group('token') if match else header).strip()


def _authorised(request) -> bool:
    """Token dari .env; dibandingkan constant-time."""
    expected = getattr(settings, 'SEISCOMP_INGEST_TOKEN', '') or ''
    if not expected:
        logger.error('SEISCOMP_INGEST_TOKEN belum diisi — ingest ditolak.')
        return False
    given = _bearer_token(request)
    try:
        return hmac.compare_digest(given, expected)
    except TypeError:            # token non-ASCII
        return False


def _clicked_at(request):
    """Parameter opsional ?clicked_at=<ISO 8601 ber-zona>. Bentuk salah -> SeiscompError."""
    raw = request.GET.get('clicked_at')
    if not raw:
        return None
    try:
        value = parse_datetime(raw)
    except ValueError:
        value = None
    if value is None or timezone.is_naive(value):
        raise SeiscompError(f'clicked_at harus ISO 8601 ber-zona: {raw!r}')
    if value > timezone.now() + timedelta(minutes=5):
        raise SeiscompError(f'clicked_at di masa depan: {raw!r}')
    return value


@csrf_exempt
@require_POST
def ingest_event(request, region):
    """POST /api/gempa/ingest/<region>/[?stage=qc&clicked_at=...] — body = isi mailexportfile.txt.

    Ber-token (Authorization: Bearer ...), idempoten lewat event_id, dan
    otomatis membuat peta GMT karena penyimpanan baris baru memicu signal
    gempa.signals.
    """
    if not _authorised(request):
        return JsonResponse({'ok': False, 'error': 'unauthorized'}, status=401)

    if region not in INGEST_REGIONS:
        return JsonResponse(
            {'ok': False, 'error': f'region tidak dikenal: {region!r}',
             'regions': sorted(INGEST_REGIONS)}, status=404)

    try:
        text = request.body.decode('utf-8')
    except UnicodeDecodeError:
        return JsonResponse(
            {'ok': False, 'error': 'body bukan teks UTF-8'}, status=400)

    if not text.strip():
        return JsonResponse({'ok': False, 'error': 'body kosong'}, status=400)

    try:
        result = ingest(region, text, stage=request.GET.get('stage', STAGE_SEND),
                        clicked_at=_clicked_at(request))
    except SeiscompError as exc:
        logger.warning('SeisComp ingest %s ditolak: %s', region, exc)
        return JsonResponse({'ok': False, 'error': str(exc)}, status=400)
    except Exception as exc:                                   # noqa: BLE001
        logger.exception('SeisComp ingest %s gagal', region)
        return JsonResponse({'ok': False, 'error': f'{type(exc).__name__}: {exc}'},
                            status=500)

    return JsonResponse({'ok': True, **result})
