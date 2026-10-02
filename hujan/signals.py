"""Kabar Telegram setiap ada data hujan BARU (input manual).

Sumber notifikasi = signal post_save, jadi berlaku untuk semua input manual:
form "Tambah Data Hujan" maupun admin Django. Impor otomatis harian TIDAK
mengabari karena memakai bulk_create (bulk operation tidak memicu signal) —
sesuai keputusan: impor harian dimatikan dan tidak perlu notifikasi.

Dua pengaman penting:

* Seluruh isi receiver dibungkus try/except. Signal ini berjalan DI DALAM
  save(); kalau ia melempar exception, penyimpanan data hujan ikut gagal.
  Notifikasi adalah efek samping — kegagalannya cukup dicatat di log.
* Dikirim lewat transaction.on_commit supaya record yang di-rollback tidak
  pernah dikabarkan.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from theme.telegram import esc, fmt_date, send_after_commit

from .models import Hujan

logger = logging.getLogger(__name__)


def format_hujan_message(record) -> str:
    """Susun pesan HTML untuk satu record hujan."""
    return (
        "🌧️ <b>DATA HUJAN BARU</b>\n"
        f"📅 {esc(fmt_date(record.tanggal))}\n"
        f"💧 Obs: <b>{esc(record.obs)} mm</b> | Hilman: {esc(record.hilman)} mm\n"
        f"🏷️ Kategori: <b>{esc(record.kategori)}</b>\n"
        f"👤 Petugas: {esc(record.petugas)}\n"
        f"📝 Keterangan: {esc(record.keterangan)}"
    )


@receiver(post_save, sender=Hujan, dispatch_uid='hujan.notify_new_record')
def notify_new_hujan(sender, instance, created, **kwargs):
    """Kirim ke Telegram hanya untuk record yang benar-benar baru."""
    if not created:
        return
    try:
        text = format_hujan_message(instance)
    except Exception as exc:                      # noqa: BLE001 - jangan gagalkan save
        logger.warning('Notifikasi hujan dilewati (gagal menyusun pesan): %s',
                       exc, exc_info=True)
        return
    send_after_commit(text)
