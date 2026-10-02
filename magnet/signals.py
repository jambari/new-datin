"""Kabar Telegram setiap ada observasi ABSOLUT BARTINGTON baru.

Hanya form Bartington (/magnet/observation/bartington/) yang dikabari — dikenali
dari `is_bartington` (pembacaan deklinasi/inklinasi dalam derajat). Form MinGeo
menulis model yang sama tapi satuannya grad, dan sengaja TIDAK dikabari.

Nilai turunan (deklinasi, inklinasi, F/H/Z/X/Y) sudah dihitung di
MagneticObservation.save() SEBELUM super().save(), jadi di signal post_save
angka-angka itu sudah tersedia untuk dikirim.

Seluruh isi receiver dibungkus try/except: signal berjalan DI DALAM save(),
jadi kegagalan menyusun pesan tidak boleh menggagalkan penyimpanan observasi.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from theme.telegram import esc, fmt_date, send_after_commit

from .models import MagneticObservation

logger = logging.getLogger(__name__)


def format_bartington_message(record) -> str:
    """Susun pesan HTML untuk satu observasi absolut Bartington."""
    return (
        "🧭 <b>OBSERVASI ABSOLUT BARTINGTON</b>\n"
        f"📅 {esc(fmt_date(record.observation_date))} | "
        f"Sesi: <b>{esc(record.session)}</b>\n"
        f"👤 Observer: {esc(record.observer)}\n"
        "----------------------------------\n"
        f"🧲 Deklinasi: <b>{esc(record.declination)}°</b> | "
        f"Inklinasi: <b>{esc(record.inclination)}°</b>\n"
        f"📈 F: <b>{esc(record.total_intensity)} nT</b> | "
        f"H: {esc(record.horizontal_intensity)} nT | "
        f"Z: {esc(record.vertical_intensity)} nT\n"
        f"➡️ X: {esc(record.north_component)} nT | "
        f"Y: {esc(record.east_component)} nT"
    )


@receiver(post_save, sender=MagneticObservation,
          dispatch_uid='magnet.notify_new_bartington')
def notify_new_bartington(sender, instance, created, **kwargs):
    """Kirim ke Telegram hanya untuk record Bartington yang baru."""
    if not created:
        return
    try:
        if not instance.is_bartington:      # MinGeo (grad) tidak dikabari
            return
        text = format_bartington_message(instance)
    except Exception as exc:                # noqa: BLE001 - jangan gagalkan save
        logger.warning('Notifikasi Bartington dilewati (gagal menyusun pesan): %s',
                       exc, exc_info=True)
        return
    send_after_commit(text)
