"""Re-run the station-health rules over metrics already stored on .189.

Use after changing qc_review/station_rules.py: days are processed oldest
first, so each day's baseline uses the re-evaluated history. Every stored
day is treated as a complete batch (channels silent within the last 60 days
are added as "no data"), like the daily job.

    python manage.py reevaluate_station_qc                 # all stored days
    python manage.py reevaluate_station_qc --since 2026-10-01
"""
from collections import defaultdict
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Max, Min

from qc_review.models import StationDailyQC
from qc_review.station_views import ingest_day


class Command(BaseCommand):
    help = "Re-evaluate stored station QC metrics with the current rules."

    def add_arguments(self, parser):
        parser.add_argument("--since", help="first day (YYYY-MM-DD); default oldest stored")
        parser.add_argument("--until", help="last day (YYYY-MM-DD); default newest stored")

    def handle(self, *args, **opts):
        span = StationDailyQC.objects.aggregate(lo=Min("day"), hi=Max("day"))
        if span["lo"] is None:
            raise CommandError("no station QC data stored")
        try:
            day = date.fromisoformat(opts["since"]) if opts["since"] else span["lo"]
            last = date.fromisoformat(opts["until"]) if opts["until"] else span["hi"]
        except ValueError:
            raise CommandError("dates must be YYYY-MM-DD")

        while day <= last:
            stations = defaultdict(list)
            for r in StationDailyQC.objects.filter(day=day).values(
                    "network", "station", "location", "channel", "sampling_rate", "metrics"):
                stations[(r["network"], r["station"])].append(
                    {"location": r["location"], "channel": r["channel"],
                     "sampling_rate": r["sampling_rate"], "metrics": r["metrics"]})
            if stations:
                batch = [{"network": n, "station": s, "channels": c} for (n, s), c in stations.items()]
                n_ch, n_diag = ingest_day(day, batch, complete=True)
                self.stdout.write(f"{day}: {len(batch)} stations, {n_ch} channels, {n_diag} findings")
            day += timedelta(days=1)
