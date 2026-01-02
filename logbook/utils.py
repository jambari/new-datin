import subprocess
import pytz
from django.conf import settings
from django.utils import timezone

def send_telegram_log(log_entry, is_update=False):
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if not token or not chat_id: return

    try:
        tz_wit = pytz.timezone('Asia/Jayapura') #
        waktu_wit = timezone.localtime(log_entry.waktu_dibuat, tz_wit)
        jam_formatted = waktu_wit.strftime('%H:%M')
    except: jam_formatted = "--:--"

    status_emoji = lambda status: "✅" if status == 'ON' else "🔴"
    def get_names(qs): return ", ".join([u.first_name if u.first_name else u.username for u in qs.all()]).title() or "-"

    handover = f"🔄 <b>Status:</b> MASUK (Ganti: {get_names(log_entry.petugas_sebelum)})" if log_entry.status_absen == 'Masuk' else f"🔄 <b>Status:</b> PULANG (Diganti: {get_names(log_entry.petugas_selanjutnya)})"

    hv_info = ""
    if log_entry.hv_counter_hour or log_entry.hv_jam_pasang or log_entry.hv_jam_angkat:
        jam_p = log_entry.hv_jam_pasang.strftime('%H:%M') if log_entry.hv_jam_pasang else "-"
        jam_a = log_entry.hv_jam_angkat.strftime('%H:%M') if log_entry.hv_jam_angkat else "-"
        hv_info = (
            f"----------------------------------\n"
            f"📊 <b>DATA HV SAMPLER:</b>\n"
            f"⏲️ Jam Pasang: <b>{jam_p}</b> | Jam Angkat: <b>{jam_a}</b>\n"
            f"⏲️ Counter: <b>{log_entry.hv_counter_hour if log_entry.hv_counter_hour else '-'}</b>\n"
            f"🌬️ Flow: <b>{log_entry.hv_flow_rate if log_entry.hv_flow_rate else '-'}</b>\n"
            f"⚖️ Berat: <b>{log_entry.hv_berat_kertas if log_entry.hv_berat_kertas else '-'} gr</b>\n"
        ) #

    header = "⚠️ <b>UPDATE LOGBOOK</b>" if is_update else "<b>LAPORAN LOGBOOK HARIAN</b>"
    msg = (
        f"{header}\n📅 {log_entry.tanggal.strftime('%d-%m-%Y')} / {jam_formatted} WIT\n"
        f"👤 {log_entry.petugas.username.title()} | 🕒 {log_entry.shift}\n{handover}\n{hv_info}"
        f"----------------------------------\n<b>Status Peralatan:</b>\n"
        f"{status_emoji(log_entry.seiscomp_seismik)} Seismik: {log_entry.seiscomp_seismik}\n"
        f"{status_emoji(log_entry.seiscomp_accelero)} Accelero: {log_entry.seiscomp_accelero}\n"
        f"{status_emoji(log_entry.esdx)} ESDX: {log_entry.esdx}\n"
        f"{status_emoji(log_entry.petir)} Petir: {log_entry.petir}\n"
        f"{status_emoji(log_entry.lemi)} LEMI: {log_entry.lemi}\n"
        f"{status_emoji(log_entry.proton)} Proton: {log_entry.proton}\n"
        f"----------------------------------\n📝 <b>Catatan:</b>\n{log_entry.catatan or '-'}"
    )

    subprocess.run(['curl', '-s', '-X', 'POST', f'https://api.telegram.org/bot{token}/sendMessage', '-d', f'chat_id={chat_id}', '-d', 'parse_mode=HTML', '--data-urlencode', f'text={msg}'])