"""Kabarkan permohonan PTSP baru ke grup Telegram: isian formulir + surat yang diunggah.

Dipanggil setelah permohonan tersimpan (lihat layanan.views). Pengiriman berjalan di
celery supaya pemohon tidak menunggu unggahan ke Telegram; bila celery tidak bisa
dihubungi, dikirim langsung. Kegagalan kirim hanya dicatat di log, permohonannya
tetap tersimpan.
"""
import logging
import mimetypes
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings

from theme.telegram import esc, send_telegram_document, send_telegram_message

logger = logging.getLogger(__name__)

WIT = ZoneInfo("Asia/Jayapura")
DASHBOARD_URL = "https://stageof-jayapura.bmkg.go.id/layanan/dashboard/{pk}/"
FIELD_MAX = 150          # caption Telegram maksimal 1024 karakter


def chat_id():
    return getattr(settings, "LAYANAN_TELEGRAM_CHAT_ID", "") or None


def caption(layanan):
    def field(label, value):
        value = str(value or "")
        if len(value) > FIELD_MAX:
            value = value[:FIELD_MAX - 1] + "…"
        return f"<b>{label}:</b> {esc(value)}"

    waktu = layanan.created_at.astimezone(WIT).strftime("%d-%m-%Y %H:%M WIT") if layanan.created_at else "-"
    return "\n".join([
        f"📥 <b>Permohonan PTSP baru #{layanan.pk}</b>",
        field("Jenis", layanan.jenis_data),
        field("Nama", layanan.nama),
        field("Instansi", layanan.instansi),
        field("Alamat", layanan.alamat),
        field("Email", layanan.email),
        field("No. HP", layanan.handphone),
        field("Waktu", waktu),
        f'<a href="{DASHBOARD_URL.format(pk=layanan.pk)}">Buka di dashboard</a>',
    ])


def send_permohonan(pk):
    """Kirim surat sebagai dokumen dengan isian formulir sebagai caption."""
    from .models import Layanan

    layanan = Layanan.objects.filter(pk=pk).first()
    if layanan is None:
        return False
    text = caption(layanan)
    path = Path(settings.PRIVATE_MEDIA_ROOT) / (layanan.surat or "")
    if layanan.surat and path.is_file():
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        name = path.name.split("_", 1)[-1]          # buang awalan acak penyimpanan
        if send_telegram_document(path.read_bytes(), name, caption=text, chat_id=chat_id(), mime=mime):
            return True
        logger.warning("Surat permohonan #%s gagal dikirim; kirim teksnya saja.", pk)
    return send_telegram_message(text + "\n<i>(surat tidak terlampir)</i>", chat_id=chat_id())


def queue_permohonan(pk):
    from .tasks import send_permohonan_task

    try:
        send_permohonan_task.delay(pk)
    except Exception as exc:                        # broker celery tidak bisa dihubungi
        logger.warning("Celery tidak tersedia (%s); notifikasi permohonan #%s dikirim langsung.", exc, pk)
        send_permohonan(pk)
