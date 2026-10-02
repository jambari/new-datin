"""Kirim pesan Telegram — dipakai bersama oleh hujan, magnet, dll.

Menggantikan pola curl berulang di beberapa app. Dua hal yang dijaga di sini:

1. **Tidak pernah melempar exception.** Notifikasi itu efek samping: kegagalan
   kirim TIDAK boleh menggagalkan penyimpanan data. Semua kegagalan masuk log.
2. **Escape HTML.** Pesan dikirim dengan parse_mode=HTML, sedangkan isinya bisa
   berasal dari input operator (nama petugas, keterangan) yang mungkin memuat
   karakter < & >. Tanpa escape, pesannya bisa rusak atau ditolak Telegram.
"""
import html
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_SEND_URL = 'https://api.telegram.org/bot{token}/sendMessage'
DEFAULT_TIMEOUT = 10


def esc(value) -> str:
    """Amankan teks untuk parse_mode=HTML (None -> '-')."""
    if value is None or value == '':
        return '-'
    return html.escape(str(value), quote=False)


def fmt_date(value) -> str:
    """Tanggal -> 'dd-mm-yyyy'.

    Menerima date/datetime maupun string. String dikembalikan apa adanya:
    record bisa saja dibuat dengan tanggal berupa string (fixture, management
    command, skrip uji), dan notifikasi tidak boleh gagal karenanya.
    """
    if value is None or value == '':
        return '-'
    strftime = getattr(value, 'strftime', None)
    if callable(strftime):
        return strftime('%d-%m-%Y')
    return str(value)


def send_telegram_message(text, chat_id=None, token=None, timeout=DEFAULT_TIMEOUT) -> bool:
    """Kirim satu pesan. Kembalikan True kalau Telegram menerimanya.

    Diam saja (return False) kalau token/chat belum dikonfigurasi, seperti
    perilaku logbook/utils.py supaya pengembangan lokal tidak error.
    """
    token = token or getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    chat_id = chat_id or getattr(settings, 'TELEGRAM_CHAT_ID', '')
    if not token or not chat_id:
        logger.info('Telegram dilewati: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID kosong.')
        return False

    try:
        resp = requests.post(
            _SEND_URL.format(token=token),
            data={'chat_id': chat_id, 'parse_mode': 'HTML', 'text': text},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        logger.warning('Telegram tidak terkirim: %s', exc)
        return False

    if resp.status_code != 200:
        logger.warning('Telegram menolak pesan (HTTP %s): %s',
                       resp.status_code, resp.text[:200])
        return False
    return True


def send_after_commit(text, **kwargs) -> None:
    """Kirim setelah transaksi database commit.

    Dipakai dari signal post_save supaya kita tidak mengabarkan record yang
    ternyata di-rollback. Catatan untuk tes: panggil
    `self.captureOnCommitCallbacks(execute=True)` supaya callback ini jalan.
    """
    from django.db import transaction

    transaction.on_commit(lambda: send_telegram_message(text, **kwargs))
