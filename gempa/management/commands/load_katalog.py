"""Import a Django fixture of the gempa catalog into PostgreSQL.

Used for the .188 -> .189 port and for later re-syncs:

    python manage.py load_katalog /path/to/gempa_dumpdata.json
    python manage.py load_katalog /path/to/gempa_dumpdata.json --flush

Why not plain `loaddata`:

* Sequences. loaddata inserts explicit primary keys, which leaves the PostgreSQL
  sequences behind, so the next INSERT in the admin would collide. This command
  resets every sequence to MAX(id) afterwards.
* Re-syncs. `--flush` empties the nine catalog tables first, so re-running is
  idempotent instead of duplicating rows.

Timezone note: the .188 dump was produced with USE_TZ=False, so its datetimes
are naive UTC. This project runs USE_TZ=True, so Django will emit
"received a naive datetime" warnings while loading — the stored values are
still correct UTC, because settings.TIME_ZONE is UTC.
"""
from django.core.management import call_command
from gempa.signals import gmt_generation_suspended
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from gempa.models import (Gempa, Balaigempa, Gempasorong, Gempanabire,
                          Satudatagempa, Gempanganjuk, Significant, City,
                          FocalMechanism)

MODELS = [Gempa, Balaigempa, Gempasorong, Gempanabire, Satudatagempa,
          Gempanganjuk, Significant, City, FocalMechanism]


class Command(BaseCommand):
    help = 'Muat fixture katalog gempa ke PostgreSQL dan rapikan sequence PK-nya.'

    def add_arguments(self, parser):
        parser.add_argument('fixtures', nargs='+',
                            help='Path ke file fixture JSON (dumpdata gempa).')
        parser.add_argument('--flush', action='store_true',
                            help='Kosongkan 9 tabel katalog dulu (untuk sinkronisasi ulang).')

    def handle(self, *args, **options):
        fixtures = options['fixtures']

        if options['flush']:
            self.stdout.write('Mengosongkan tabel katalog...')
            with transaction.atomic():
                for model in MODELS:
                    deleted, _ = model.objects.all().delete()
                    self.stdout.write(f'  {model.__name__:16s} dihapus: {deleted}')

        self.stdout.write('Memuat fixture...')
        # loaddata memanggil save() per objek, jadi tanpa ini 113.000 event akan
        # menjadwalkan 113.000 render GMT. Peta arsipnya sendiri sudah disalin
        # dari .188, dan gmt.generate() melewati berkas yang sudah ada.
        with gmt_generation_suspended():
            for fixture in fixtures:
                try:
                    call_command('loaddata', fixture, verbosity=0)
                except Exception as exc:
                    raise CommandError(f'Gagal memuat {fixture}: {exc}')
                self.stdout.write(f'  dimuat: {fixture}')

        self.stdout.write('Merapikan sequence PK...')
        for model in MODELS:
            table = model._meta.db_table
            pk = model._meta.pk.column
            with connection.cursor() as cur:
                cur.execute('SELECT pg_get_serial_sequence(%s, %s)', [table, pk])
                sequence = cur.fetchone()[0]
                if not sequence:
                    self.stdout.write(f'  {table:28s} tidak ada sequence, dilewati')
                    continue
                cur.execute(
                    f'SELECT setval(%s, COALESCE((SELECT MAX("{pk}") FROM "{table}"), 1))',
                    [sequence],
                )
                newval = cur.fetchone()[0]
            self.stdout.write(f'  {table:28s} sequence -> {newval}')

        self.stdout.write(self.style.SUCCESS('Selesai. Jumlah baris sekarang:'))
        total = 0
        for model in MODELS:
            count = model.objects.count()
            total += count
            self.stdout.write(f'  {model.__name__:16s} {count:>8,}')
        self.stdout.write(f'  {"TOTAL":16s} {total:>8,}')
