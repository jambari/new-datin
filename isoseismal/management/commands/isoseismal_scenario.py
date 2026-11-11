"""Buat peta isoseismal skenario dari run ShakeMap skenario di .50.

Dipanggil tombol ISOSEISMAL di halaman /generated/ .50 lewat ssh:
    manage.py isoseismal_scenario 2026092907000020260929070000 --name "Sesar Mamberamo Segmen Mawe"
grid.xml diambil dari data_MMI/<run>/output di .50 (ssh host50). Peta baru disembunyikan sampai staf
menerbitkannya di admin. Baris terakhir keluaran: ISOSEISMAL_RESULT {json} untuk dibaca .50.
"""
import json
import subprocess

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from isoseismal.services import store_scenario


class Command(BaseCommand):
    help = 'Buat/perbarui peta isoseismal skenario dari run ShakeMap skenario di .50.'

    def add_arguments(self, parser):
        parser.add_argument('run', help='Nama folder run di data_MMI .50, mis. 2026092907000020260929070000')
        parser.add_argument('--name', default='', help='Nama skenario (isian Place di form Scenario .50).')

    def handle(self, *args, run, name, **opts):
        try:
            obj, status = store_scenario(run, name)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            self.stdout.write('ISOSEISMAL_RESULT ' + json.dumps({'ok': False, 'error': str(exc)}))
            raise CommandError(f'{run}: {exc}')
        base = getattr(settings, 'PUBLIC_SITE_URL', 'https://stageof-jayapura.bmkg.go.id').rstrip('/')
        result = {'ok': True, 'status': status, 'title': obj.title, 'hidden': obj.is_hidden,
                  'url': base + obj.get_absolute_url(), 'admin': f'{base}/admin/isoseismal/isoseismalmap/{obj.pk}/change/'}
        self.stdout.write('ISOSEISMAL_RESULT ' + json.dumps(result))
