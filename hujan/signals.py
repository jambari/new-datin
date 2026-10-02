"""Kabar Telegram setiap ada data hujan BARU (input manual).

Sumber notifikasi = signal post_save, jadi berlaku untuk semua input manual:
form "Tambah Data Hujan" maupun admin Django. Impor otomatis harian TIDAK
mengabari karena memakai bulk_create (bulk operation tidak memicu signal) —
sesuai keputusan: impor harian dimatikan dan tidak perlu notifikasi.

Notifikasi dilewatkan transaction.on_commit: kalau transaksinya batal, tidak ada
kabar palsu.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from theme.telegram import esc, send_after_commit

from .models import Hujan


def format_hujan_message(record) -> str:
    """Susun pesan HTML untuk satu record hujan."""
    return (
        "🌧️ <b>DATA HUJAN BARU</b>\n"
        f"📅 {esc(record.tanggal.strftime('%d-%m-%Y'))}\n"
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
    send_after_commit(format_hujan_message(instance))
