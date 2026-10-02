"""App config + the operator groups, mirroring the permissions on .188.

On 36.91.166.188 each regional office has its OWN permission set on its own
catalog table, so an operator can only edit their office's events:

    angkasa  view balaigempa + full CRUD city/gempa/satudatagempa/significant
    pgr5     full CRUD balaigempa/city/satudatagempa/significant
    nabire   full CRUD gempanabire + satudatagempa
    sorong   full CRUD gempasorong + satudatagempa

Here that is expressed as one group per office (same effective permissions,
easier to administer: add a user to the group instead of setting 8-17
individual permissions).

Each office also declares the page it lands on after logging in at
/accounts/login/ — its own catalog, not the admin index.
"""
from django.apps import AppConfig
from django.db.models.signals import post_migrate

#: Satu grup per kantor: izinnya sama dengan akun per-user di .188, plus
#: halaman katalog yang jadi tujuan setelah login.
OPERATOR_GROUPS = {
    'Operator Angkasa': {
        'permissions': [
            'view_balaigempa',
            'add_city', 'change_city', 'delete_city', 'view_city',
            'add_gempa', 'change_gempa', 'delete_gempa', 'view_gempa',
            'add_satudatagempa', 'change_satudatagempa', 'delete_satudatagempa', 'view_satudatagempa',
            'add_significant', 'change_significant', 'delete_significant', 'view_significant',
        ],
        'landing': 'gempa_admin:gempa_gempa_changelist',          # /gempa-admin/gempa/gempa/
    },
    'Operator PGR V': {
        'permissions': [
            'add_balaigempa', 'change_balaigempa', 'delete_balaigempa', 'view_balaigempa',
            'add_city', 'change_city', 'delete_city', 'view_city',
            'add_satudatagempa', 'change_satudatagempa', 'delete_satudatagempa', 'view_satudatagempa',
            'add_significant', 'change_significant', 'delete_significant', 'view_significant',
        ],
        'landing': 'gempa_admin:gempa_balaigempa_changelist',
    },
    'Operator Nabire': {
        'permissions': [
            'add_gempanabire', 'change_gempanabire', 'delete_gempanabire', 'view_gempanabire',
            'add_satudatagempa', 'change_satudatagempa', 'delete_satudatagempa', 'view_satudatagempa',
        ],
        'landing': 'gempa_admin:gempa_gempanabire_changelist',
    },
    'Operator Sorong': {
        'permissions': [
            'add_gempasorong', 'change_gempasorong', 'delete_gempasorong', 'view_gempasorong',
            'add_satudatagempa', 'change_satudatagempa', 'delete_satudatagempa', 'view_satudatagempa',
        ],
        'landing': 'gempa_admin:gempa_gempasorong_changelist',
    },
}

#: Grup awal (semua izin katalog) — digantikan grup per-kantor di atas.
LEGACY_GROUP_NAME = 'Operator Katalog Gempa'


def landing_url_name_for(group_names):
    """Nama URL katalog milik kantor user, atau None kalau bukan operator.

    Urutan mengikuti definisi OPERATOR_GROUPS, jadi user yang kebetulan ada di
    beberapa grup dapat tujuan yang konsisten.
    """
    for group_name, spec in OPERATOR_GROUPS.items():
        if group_name in group_names:
            return spec['landing']
    return None


def ensure_operator_groups(sender, using=None, **kwargs):
    """Buat/rapikan grup per-kantor setiap kali `migrate` dijalankan.

    Lewat post_migrate, bukan data migration: izin model baru dibuat Django pada
    post_migrate (create_permissions), jadi data migration bisa berjalan saat
    izin belum ada. Idempoten.
    """
    from django.apps import apps as global_apps
    from django.contrib.auth.management import create_permissions
    from django.contrib.auth.models import Group, Permission

    app_config = global_apps.get_app_config('gempa')
    create_permissions(app_config, verbosity=0, apps=global_apps)

    available = dict(
        Permission.objects.filter(content_type__app_label='gempa')
        .values_list('codename', 'id')
    )

    missing = []
    for name, spec in OPERATOR_GROUPS.items():
        group, _ = Group.objects.get_or_create(name=name)
        ids = []
        for codename in spec['permissions']:
            if codename in available:
                ids.append(available[codename])
            else:
                missing.append(f'{name}:{codename}')
        # list() of ids, bukan queryset: M2M set() menolak queryset beda alias DB
        group.permissions.set(ids)

    if missing:
        import sys
        print(f'[gempa] PERINGATAN izin tidak ditemukan: {missing}', file=sys.stderr)

    # Grup versi pertama (semua izin) tidak dipakai lagi.
    Group.objects.filter(name=LEGACY_GROUP_NAME).delete()


class GempaConfig(AppConfig):
    """Katalog gempa — cermin (standby) dari datin_django/gempa di 36.91.166.188.

    Dijalankan di server 36.91.166.189 dengan PostgreSQL, supaya katalog tetap
    bisa dikelola operator ketika server .188 mati.
    """

    default_auto_field = 'django.db.models.AutoField'
    name = 'gempa'
    verbose_name = 'Katalog Gempa'

    def ready(self):
        post_migrate.connect(
            ensure_operator_groups,
            sender=self,
            dispatch_uid='gempa.ensure_operator_groups',
        )
