"""Isi ulang katalog Gempa JAY dari log tombol SeisComp. Tanpa --apply hanya melaporkan."""
import collections
import csv
import json

from django.core.management.base import BaseCommand
from django.db import transaction

from gempa.backfill import INVALID, apply_event, plan_event
from gempa.models import Gempa


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('plan', help='JSON dari scripts/seiscomp_backfill_extract.py')
        parser.add_argument('--apply', action='store_true', help='Tulis ke database')
        parser.add_argument('--report', help='Tulis laporan CSV ke berkas ini')

    def handle(self, *args, **options):
        with open(options['plan'], encoding='utf-8') as fh:
            items = json.load(fh)
        rows = {r.event_id: r for r in Gempa.objects.filter(
            event_id__in=[i['event_id'] for i in items])}
        plans = [(i, plan_event(i, rows.get(i['event_id']))) for i in items]

        counts = collections.Counter(p['action'] for _i, p in plans)
        self.stdout.write(', '.join(f'{k}={v}' for k, v in sorted(counts.items())))
        if options['report']:
            with open(options['report'], 'w', newline='', encoding='utf-8') as fh:
                writer = csv.writer(fh)
                writer.writerow(['event_id', 'action', 'pk', 'clicks', 'first_click',
                                 'last_qc', 'set_kirim', 'set_qc', 'changes'])
                for _i, p in plans:
                    writer.writerow([p['event_id'], p['action'], p['pk'], p['clicks'],
                                     p['first_click'], p['last_qc'], p['set_kirim'],
                                     p['set_qc'], json.dumps(p['changes'], default=str)])
        if not options['apply']:
            self.stdout.write('Dry run: tidak ada yang ditulis.')
            return
        for item, plan in plans:
            if plan['action'] == INVALID:
                continue
            with transaction.atomic():
                apply_event(item, plan)
        self.stdout.write(self.style.SUCCESS('Selesai.'))
