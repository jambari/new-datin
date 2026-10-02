from django.apps import AppConfig
from django.db.models.signals import post_migrate

#: Grup pemilik akses katalog gempa. Dibuat/dirapikan otomatis setiap `migrate`.
KATALOG_GROUP_NAME = 'Operator Katalog Gempa'


def ensure_operator_group(sender, using=None, **kwargs):
    """Pastikan grup operator ada dan memuat SEMUA izin model katalog.

    Sengaja lewat post_migrate, bukan data migration: izin model baru dibuat
    Django pada post_migrate (create_permissions) SETELAH migrasi selesai, jadi
    data migration bisa berjalan saat izin belum lengkap — persis yang terjadi
    pada percobaan pertama (hanya 20 dari 36 izin yang terpasang).

    Idempoten: aman dijalankan berulang kali.
    """
    from django.apps import apps as global_apps
    from django.contrib.auth.management import create_permissions
    from django.contrib.auth.models import Group, Permission

    # Pastikan baris Permission untuk app ini sudah ada sebelum dipakai.
    # (urutan receiver post_migrate antar app tidak dijamin)
    app_config = global_apps.get_app_config('gempa')
    create_permissions(app_config, verbosity=0, apps=global_apps)

    group, _ = Group.objects.get_or_create(name=KATALOG_GROUP_NAME)
    # list(), bukan queryset: M2M set() menolak queryset yang terikat alias DB
    # berbeda dan bisa berhenti separuh jalan. Proyek ini single-database.
    permissions = list(Permission.objects.filter(content_type__app_label='gempa'))
    group.permissions.set(permissions)


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
            ensure_operator_group,
            sender=self,
            dispatch_uid='gempa.ensure_operator_group',
        )
