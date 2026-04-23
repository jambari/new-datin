import openpyxl
from django.core.management.base import BaseCommand
from repository.models import ReferenceLocation


class Command(BaseCommand):
    help = 'Import reference locations from cities.xlsx'

    def add_arguments(self, parser):
        parser.add_argument('xlsx_path', type=str)

    def handle(self, *args, **options):
        path = options['xlsx_path']
        wb = openpyxl.load_workbook(path)
        ws = wb.active

        created = 0
        skipped = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            lat, lon, name = row[0], row[1], row[2]
            if not name or lat is None or lon is None:
                skipped += 1
                continue
            _, was_created = ReferenceLocation.objects.update_or_create(
                name=str(name).strip(),
                defaults={'latitude': float(lat), 'longitude': float(lon)},
            )
            if was_created:
                created += 1

        self.stdout.write(self.style.SUCCESS(
            f'Done: {created} created, {skipped} skipped. Total: {ReferenceLocation.objects.count()}'
        ))
