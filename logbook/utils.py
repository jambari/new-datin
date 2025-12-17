import subprocess
import pytz
from django.conf import settings
from django.utils import timezone

def send_telegram_log(log_entry, is_update=False): # Tambah parameter is_update
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    
    if not token or not chat_id:
        return

    # --- KONVERSI WAKTU KE WIT ---
    tz_wit = pytz.timezone('Asia/Jayapura')
    waktu_wit = timezone.localtime(log_entry.waktu_dibuat, tz_wit)
    jam_formatted = waktu_wit.strftime('%H:%M')

    status_emoji = lambda status: "✅" if status == 'ON' else "🔴"

    # --- LOGIC HANDOVER ---
    handover_info = ""
    if log_entry.status_absen == 'Masuk':
        prev_name = log_entry.petugas_sebelum.username if log_entry.petugas_sebelum else "-"
        prev_name = prev_name.title() 
        handover_info = f"🔄 <b>Status:</b> MASUK (Menggantikan: {prev_name})"
    else:
        next_name = log_entry.petugas_selanjutnya.username if log_entry.petugas_selanjutnya else "-"
        next_name = next_name.title()
        handover_info = f"🔄 <b>Status:</b> PULANG (Digantikan: {next_name})"

    nama_petugas = log_entry.petugas.username.title() if log_entry.petugas else 'System'

    # --- LOGIC HEADER PESAN (BARU) ---
    if is_update:
        header_text = "⚠️ <b>UPDATE LOGBOOK</b> (Revisi Data)"
    else:
        header_text = "<b>LAPORAN LOGBOOK HARIAN</b>"

    # --- SUSUN PESAN ---
    message = (
        f"{header_text}\n"
        f"📅 Waktu: {log_entry.tanggal.strftime('%d-%m-%Y')} / {jam_formatted} WIT\n"
        f"👤 Petugas: {nama_petugas}\n"
        f"🕒 Shift: {log_entry.shift}\n"
        f"{handover_info}\n"
        f"----------------------------------\n"
        f"<b>Status Peralatan:</b>\n"
        f"{status_emoji(log_entry.seiscomp_seismik)} Seiscomp Seismik: <b>{log_entry.seiscomp_seismik}</b>\n"
        f"{status_emoji(log_entry.seiscomp_accelero)} Seiscomp Accelero: <b>{log_entry.seiscomp_accelero}</b>\n"
        f"{status_emoji(log_entry.esdx)} ESDX: <b>{log_entry.esdx}</b>\n"
        f"{status_emoji(log_entry.petir)} Petir: <b>{log_entry.petir}</b>\n"
        f"{status_emoji(log_entry.lemi)} LEMI: <b>{log_entry.lemi}</b>\n"
        f"{status_emoji(log_entry.proton)} Proton: <b>{log_entry.proton}</b>\n"
        f"----------------------------------\n"
        f"📝 <b>Catatan:</b>\n"
        f"{log_entry.catatan if log_entry.catatan else '-'}"
    )

    # --- KIRIM PAKAI CURL ---
    curl_command = [
        'curl', '-s', '-X', 'POST',
        f'https://api.telegram.org/bot{token}/sendMessage',
        '-d', f'chat_id={chat_id}',
        '-d', 'parse_mode=HTML',
        '--data-urlencode', f'text={message}'
    ]

    try:
        subprocess.run(curl_command, check=True, capture_output=True)
    except Exception as e:
        print(f"Telegram Curl Error: {e}")