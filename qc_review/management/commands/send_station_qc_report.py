"""Send (or preview) the daily station-health PDF report.

    python manage.py send_station_qc_report                    # yesterday UTC → Telegram
    python manage.py send_station_qc_report --day 2026-10-11
    python manage.py send_station_qc_report --out /tmp/r.pdf   # write PDF only, no Telegram
"""
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from qc_review import station_report


class Command(BaseCommand):
    help = "Send the daily station waveform-health report (PDF) to Telegram."

    def add_arguments(self, parser):
        parser.add_argument("--day", help="YYYY-MM-DD (UTC); default yesterday")
        parser.add_argument("--out", help="write the PDF to this path instead of sending")

    def handle(self, *args, **opts):
        try:
            day = (date.fromisoformat(opts["day"]) if opts["day"]
                   else timezone.now().date() - timedelta(days=1))
        except ValueError:
            raise CommandError("--day must be YYYY-MM-DD")

        if opts["out"]:
            data = station_report.report_data(day)
            if not data["n_channels"]:
                raise CommandError(f"no station QC data for {day}")
            with open(opts["out"], "wb") as fh:
                fh.write(station_report.build_pdf(day, data))
            self.stdout.write(f"wrote {opts['out']} ({len(data['findings'])} findings)")
            return

        # A manual run always sends (resend), unlike the scheduled task.
        ok = station_report.send_daily_report(day, force=True)
        self.stdout.write(f"report {day}: {'sent' if ok else 'NOT sent (see log)'}")
