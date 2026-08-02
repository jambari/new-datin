"""
Sends an hourly Telegram status report for all monitored instruments.

Usage (cron every hour):
    0 * * * * cd /var/www/html && source venv/bin/activate && \
              python manage.py send_instrument_report >> /var/log/instrument_report.log 2>&1
"""

import subprocess
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
import zoneinfo

from magnet.models import InstrumentStatus

_WIT = zoneinfo.ZoneInfo('Asia/Jayapura')
_STALE_MINUTES = 5

_LABELS = {
    InstrumentStatus.LEMI:     'LEMI-018',
    InstrumentStatus.PROTON:   'Proton',
    InstrumentStatus.NEXSTORM: 'Nexstorm',
}
_STATUS_EMOJI = {
    'ok':             '✅',
    'not_responding': '⚠️',
    'not_running':    '❌',
    'monitor_offline':'🔌',
    'unknown':        '❓',
}
_STATUS_LABEL = {
    'ok':             'OK',
    'not_responding': 'Tidak Merespons',
    'not_running':    'Tidak Berjalan',
    'monitor_offline':'Monitor Offline',
    'unknown':        'Tidak Diketahui',
}


def _get_status(instrument):
    try:
        latest = InstrumentStatus.objects.filter(instrument=instrument).latest('reported_at')
        stale  = (timezone.now() - latest.reported_at) > timedelta(minutes=_STALE_MINUTES)
        status = 'monitor_offline' if stale else latest.status
        return status, latest.computer_name, latest.reported_at
    except InstrumentStatus.DoesNotExist:
        return 'unknown', '', None


class Command(BaseCommand):
    help = 'Send hourly instrument status report to Telegram'

    def handle(self, *args, **options):
        token   = settings.TELEGRAM_BOT_TOKEN
        chat_id = settings.TELEGRAM_CHAT_ID
        if not token or not chat_id:
            self.stderr.write('TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set.')
            return

        now_wit = timezone.now().astimezone(_WIT)
        lines   = [f"📊 <b>Laporan Status Instrumen</b> — {now_wit.strftime('%H:%M')} WIT\n"]

        all_ok = True
        for instr in (InstrumentStatus.LEMI, InstrumentStatus.PROTON, InstrumentStatus.NEXSTORM):
            status, computer, reported_at = _get_status(instr)
            if status != 'ok':
                all_ok = False
            emoji = _STATUS_EMOJI.get(status, '❓')
            label = _STATUS_LABEL.get(status, status)
            name  = _LABELS[instr]
            pc    = f' — {computer}' if computer else ''
            time_str = ''
            if reported_at:
                time_str = ' (update: ' + reported_at.astimezone(_WIT).strftime('%H:%M:%S') + ')'
            lines.append(f"{emoji} <b>{name}</b>: {label}{pc}{time_str}")

        if all_ok:
            self.stdout.write(f'All instruments OK — skipping report at {now_wit.strftime("%Y-%m-%d %H:%M:%S")} WIT')
            return

        lines.append('\n⚠️ Ada instrumen yang memerlukan perhatian!')

        msg = '\n'.join(lines)

        subprocess.run([
            'curl', '-s', '-X', 'POST',
            f'https://api.telegram.org/bot{token}/sendMessage',
            '-d', f'chat_id={chat_id}',
            '-d', 'parse_mode=HTML',
            '--data-urlencode', f'text={msg}',
        ], check=False)

        self.stdout.write(f'Report sent at {now_wit.strftime("%Y-%m-%d %H:%M:%S")} WIT')
