import subprocess
import zoneinfo
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone

_WIT = zoneinfo.ZoneInfo("Asia/Jayapura")

_CAKE_EMOJIS = ["🎂", "🎉", "🎊", "🥳", "🎈"]


class Command(BaseCommand):
    help = 'Send birthday congratulation to Telegram group for pegawai with birthday today (WIT)'

    def handle(self, *args, **options):
        token   = settings.TELEGRAM_BOT_TOKEN
        chat_id = settings.TELEGRAM_CHAT_ID
        if not token or not chat_id:
            self.stderr.write('TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set.')
            return

        from jadwal.models import Pegawai

        today_wit = timezone.now().astimezone(_WIT).date()
        mmdd = today_wit.strftime('%m%d')

        celebrants = list(
            Pegawai.objects.filter(nip__regex=r'^\d{4}' + mmdd)
            .order_by('urutan', 'nama')
        )

        if not celebrants:
            self.stdout.write(f'No birthdays today ({today_wit}).')
            return

        lines = ["🎂🎉 <b>SELAMAT ULANG TAHUN!</b> 🎉🎂\n"]
        for p in celebrants:
            birth_year = int(p.nip[:4])
            age = today_wit.year - birth_year
            lines.append(f"🎈 <b>{p.nama}</b> — {age} tahun")

        lines.append(
            "\nSemoga panjang umur, sehat selalu, dan sukses dalam tugas. "
            "Semoga setiap hari membawa kebahagiaan dan keberkahan. 🙏"
        )

        msg = '\n'.join(lines)

        subprocess.run([
            'curl', '-s', '-X', 'POST',
            f'https://api.telegram.org/bot{token}/sendMessage',
            '-d', f'chat_id={chat_id}',
            '-d', 'parse_mode=HTML',
            '--data-urlencode', f'text={msg}',
        ], check=False)

        names = ', '.join(p.nama for p in celebrants)
        self.stdout.write(f'Birthday wishes sent for: {names}')
