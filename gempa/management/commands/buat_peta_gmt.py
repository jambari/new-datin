"""Buat peta GMT untuk event katalog — port dari alur .188 (buat_peta.sh).

Contoh:

    # satu event (pk database)
    python manage.py buat_peta_gmt jay --pk 28066

    # lewat event_id SeisComp
    python manage.py buat_peta_gmt balai --event-id 20261002213717.000000

    # semua event pada rentang tanggal yang petanya belum ada
    python manage.py buat_peta_gmt sorong --date-from 2026-10-01 --date-to 2026-10-02

    # paksa buat ulang walau berkasnya sudah ada
    python manage.py buat_peta_gmt nabire --pk 1 --force
"""
import datetime

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError

from gempa import gmt


class Command(BaseCommand):
    help = 'Buat peta GMT (buat_peta.sh) untuk event katalog gempa.'

    def add_arguments(self, parser):
        parser.add_argument('region', choices=sorted(gmt.REGIONS),
                            help='jay | balai | nabire | sorong')
        parser.add_argument('--pk', type=int, help='Primary key event.')
        parser.add_argument('--event-id', help='event_id SeisComp.')
        parser.add_argument('--model', help='Nama model (default: sesuai region).')
        parser.add_argument('--date-from', help='Batas awal tanggal (YYYY-MM-DD).')
        parser.add_argument('--date-to', help='Batas akhir tanggal (YYYY-MM-DD).')
        parser.add_argument('--limit', type=int, help='Batasi jumlah event pada mode rentang.')
        parser.add_argument('--force', action='store_true',
                            help='Buat ulang walau berkasnya sudah ada.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Tampilkan rencana tanpa menjalankan GMT.')

    # ── helpers ──────────────────────────────────────────────────────────────

    def _model(self, options):
        name = options.get('model') or gmt.REGION_MODEL[options['region']]
        try:
            return apps.get_model('gempa', name)
        except LookupError:
            raise CommandError(f'Model tidak dikenal: {name}')

    def _one(self, model, options, region):
        if options.get('pk'):
            obj = model.objects.filter(pk=options['pk']).first()
            if obj is None:
                raise CommandError(f'{model.__name__} pk={options["pk"]} tidak ditemukan')
        elif options.get('event_id'):
            obj = model.objects.filter(event_id=options['event_id']).first()
            if obj is None:
                raise CommandError(f'{model.__name__} event_id={options["event_id"]} tidak ditemukan')
        else:
            raise CommandError('Sebutkan --pk atau --event-id (atau pakai --date-from).')
        return [obj]

    def _range(self, model, options):
        qs = model.objects.all()
        if options.get('date_from'):
            qs = qs.filter(tanggal__gte=options['date_from'])
        if options.get('date_to'):
            qs = qs.filter(tanggal__lte=options['date_to'])
        qs = qs.order_by('tanggal', 'origin')
        if options.get('limit'):
            qs = qs[:options['limit']]
        return list(qs)

    def _generate(self, obj, region, options, counters):
        label = f'{obj.tanggal} {obj.origin}'
        try:
            if options['dry_run']:
                target = gmt.map_filename(region, obj.tanggal, obj.origin)
                exists = gmt.map_exists(region, obj.tanggal, obj.origin)
                self.stdout.write(f'  [dry-run] {label} -> {target}'
                                  f'{" (sudah ada)" if exists and not options["force"] else ""}')
                counters['skipped'] += 1
                return
            result = gmt.generate(
                region,
                lat=obj.lintang, lon=obj.bujur, mag=obj.magnitudo,
                tanggal=obj.tanggal, origin=obj.origin, depth=obj.depth,
                force=options['force'],
            )
        except gmt.GmtError as exc:
            counters['failed'] += 1
            self.stderr.write(self.style.ERROR(f'  GAGAL {label}: {exc}'))
            return
        if result.skipped:
            counters['skipped'] += 1
            self.stdout.write(f'  lewat  {label} — {result.detail}')
        else:
            counters['created'] += 1
            self.stdout.write(self.style.SUCCESS(f'  dibuat {label} -> {result.filename} ({result.seconds:.1f}s)'))

    # ── entry point ──────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        region = options['region']
        model = self._model(options)
        self.stdout.write(f'{model.__name__} / region {region} (prefix {gmt.prefix_for(region)})')

        try:
            if options.get('date_from') or options.get('date_to'):
                objects = self._range(model, options)
            else:
                objects = self._one(model, options, region)
        except ValueError as exc:
            raise CommandError(f'Tanggal tidak valid: {exc}')

        if not objects:
            self.stdout.write('  tidak ada event yang cocok.')
            return

        counters = {'created': 0, 'skipped': 0, 'failed': 0}
        for obj in objects:
            self._generate(obj, region, options, counters)

        summary = (f"selesai: {counters['created']} dibuat, {counters['skipped']} dilewat, "
                   f"{counters['failed']} gagal")
        style = self.style.ERROR if counters['failed'] else self.style.SUCCESS
        self.stdout.write(style(summary))
        if counters['failed']:
            raise CommandError(summary)
