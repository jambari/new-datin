"""Import catalog operator accounts from .188 into this project.

    python manage.py import_operators /home/sysop/gempa_fixtures/operators.json

The JSON is produced by scripts/export on .188 (see the port notes) and holds
username, password hash, email, names, flags and the account's .188
permissions. Django password hashes are portable, so operators keep their
existing .188 passwords — no password reset, no new credentials to distribute.

Each account is placed in its per-office group (see gempa/apps.OPERATOR_GROUPS)
rather than getting individual permissions, which is equivalent but easier to
administer.

The username 'angkasa' also exists on this server for a different person. It is
renamed to 'angkasa_lama' and deactivated instead of deleted, because
theme.ActivityLog has rows pointing at it (its own audit trail) which must not
be destroyed. The rename frees the username for the .188 account.
"""
import json

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from gempa.apps import OPERATOR_GROUPS

#: username on .188 -> group here
USER_GROUP = {
    'angkasa': 'Operator Angkasa',
    'pgr5':    'Operator PGR V',
    'nabire':  'Operator Nabire',
    'sorong':  'Operator Sorong',
}

#: Nama akun lama di server ini yang harus dibebaskan (bukan orang yang sama).
PARKED_USERNAME = 'angkasa'
PARKED_RENAME = 'angkasa_lama'


class Command(BaseCommand):
    help = 'Impor akun operator katalog dari .188 (dengan hash password aslinya).'

    def add_arguments(self, parser):
        parser.add_argument('fixture', help='Path ke JSON hasil ekspor dari .188')
        parser.add_argument('--dry-run', action='store_true',
                            help='Tampilkan rencana tanpa mengubah apa pun.')

    def handle(self, *args, **options):
        path = options['fixture']
        dry_run = options['dry_run']

        try:
            with open(path) as fh:
                accounts = json.load(fh)
        except FileNotFoundError:
            raise CommandError(f'Tidak ditemukan: {path}')
        except json.JSONDecodeError as exc:
            raise CommandError(f'JSON tidak valid: {exc}')

        if not isinstance(accounts, list) or not accounts:
            raise CommandError('Fixture harus berisi daftar akun.')

        incoming_usernames = {a['username'] for a in accounts}

        # 1. Bebaskan username 'angkasa' milik akun lama server ini.
        if PARKED_USERNAME in incoming_usernames:
            clash = User.objects.filter(username=PARKED_USERNAME).first()
            if clash:
                if User.objects.filter(username=PARKED_RENAME).exists():
                    raise CommandError(
                        f'{PARKED_RENAME} sudah ada — selesaikan manual dulu.')
                self.stdout.write(
                    f'Mengganti nama akun lama {PARKED_USERNAME!r} (id={clash.pk}) '
                    f'-> {PARKED_RENAME!r} + nonaktif (riwayat ActivityLog tetap utuh)')
                if not dry_run:
                    clash.username = PARKED_RENAME
                    clash.is_active = False
                    clash.save(update_fields=['username', 'is_active'])
            else:
                self.stdout.write(f'Tidak ada akun {PARKED_USERNAME!r} untuk dibebaskan.')

        # 2. Buat/perbarui tiap akun.
        created_n = updated_n = 0
        for account in accounts:
            username = account['username']
            group_name = USER_GROUP.get(username)
            if group_name is None:
                self.stdout.write(self.style.WARNING(
                    f'  {username}: tidak ada pemetaan grup, dilewati'))
                continue
            if group_name not in OPERATOR_GROUPS:
                raise CommandError(f'Grup {group_name!r} tidak dikenal.')

            user = User.objects.filter(username=username).first()
            is_new = user is None
            if is_new:
                user = User(username=username)

            if not dry_run:
                user.password = account['password']      # hash dari .188, apa adanya
                user.email = account.get('email') or ''
                user.first_name = account.get('first_name') or ''
                user.last_name = account.get('last_name') or ''
                user.is_active = bool(account.get('is_active', True))
                user.is_staff = True
                # Sengaja TIDAK mengimpor superuser: akun .188 'admin' dikecualikan,
                # dan operator hanya perlu akses katalog.
                user.is_superuser = False
                joined = account.get('date_joined')
                if joined:
                    parsed = parse_datetime(joined)
                    if parsed:
                        user.date_joined = parsed
                user.save()

                group, _ = Group.objects.get_or_create(name=group_name)
                user.groups.set([group])

            created_n += is_new
            updated_n += not is_new
            perms = len(OPERATOR_GROUPS[group_name])
            self.stdout.write(
                f'  {"buat " if is_new else "perbarui"} {username:8s} '
                f'groups=[{group_name}] ({perms} izin) staff=True super=False')

        verb = 'DRY-RUN: akan ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f'{verb}dibuat: {created_n}, diperbarui: {updated_n}, total: {len(accounts)}'))
