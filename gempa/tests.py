"""Tests for the ported gempa catalog app (.188 -> .189).

Focus areas:
* the dedicated /gempa-admin/ site works WITHOUT OTP, while the existing
  /admin/ site (OTP) is untouched and does not gain the catalog models;
* the admin index shows only the gempa catalog;
* the notify endpoint and the GeoJSON API behave;
* the group-based post-login redirect.
"""
import datetime
import json
import os

from django.contrib import admin as django_admin
from django.contrib.auth.models import Group, User
import pathlib
import re
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .apps import (ensure_operator_groups, OPERATOR_GROUPS,
                  LEGACY_GROUP_NAME)
from .sites import gempa_admin_site
from .models import (Gempa, Balaigempa, Gempasorong, Gempanabire,
                     Satudatagempa, Gempanganjuk, Significant, City,
                     FocalMechanism)

CATALOG_MODELS = [Gempa, Balaigempa, Gempasorong, Gempanabire,
                  Satudatagempa, Gempanganjuk, Significant, City, FocalMechanism]

#: Grup operator yang dipakai di test (Angkasa punya akses ke Gempa JAY).
ANGKASA_GROUP = 'Operator Angkasa'


def make_event(model, **kwargs):
    """Create one catalog row with the minimum required fields."""
    defaults = dict(
        event_id=f'ev-{model.__name__.lower()}',
        tanggal=datetime.date(2026, 10, 1),
        origin='10:00:00',
        lintang='-2.50',
        bujur='140.70',
        magnitudo='4.5',
        depth=10,
        ket='uji',
    )
    defaults.update(kwargs)
    return model.objects.create(**defaults)


class GempaAdminSiteTest(TestCase):
    """Admin katalog terpisah, tanpa OTP; /admin/ yang lama tidak berubah."""

    def setUp(self):
        self.staff = User.objects.create_user('operator', password='pass12345',
                                             is_staff=True)
        self.staff.groups.add(Group.objects.get(name=ANGKASA_GROUP))

    def test_login_page_renders_without_otp(self):
        resp = self.client.get('/gempa-admin/login/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id_username')
        # tidak ada langkah OTP apa pun
        self.assertNotContains(resp, 'otp_token')

    def test_anonymous_is_redirected_to_login(self):
        resp = self.client.get('/gempa-admin/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/gempa-admin/login/', resp['Location'])

    def test_staff_can_open_index_and_changelist(self):
        self.client.force_login(self.staff)

        resp = self.client.get('/gempa-admin/')
        self.assertEqual(resp.status_code, 200)

        resp = self.client.get('/gempa-admin/gempa/gempa/')
        self.assertEqual(resp.status_code, 200)

    def test_index_lists_only_the_catalog(self):
        """Halaman admin ini hanya menampilkan katalog gempa."""
        self.client.force_login(self.staff)
        resp = self.client.get('/gempa-admin/')
        # app lain di project ini tidak boleh muncul di sini
        for absent in ['Logbook', 'Repository', 'Jadwal', 'Perjadin', 'Tiket']:
            self.assertNotContains(resp, absent)
        # katalognya sendiri muncul
        self.assertContains(resp, 'Gempa JAY')

    def test_index_is_scoped_to_the_operators_own_office(self):
        """Angkasa hanya melihat katalog yang jadi haknya, bukan kantor lain."""
        self.client.force_login(self.staff)          # anggota Operator Angkasa
        body = self.client.get('/gempa-admin/').content.decode()

        for visible in ['Gempa JAY', 'Gempa PGR V (Balai)', 'Gempa Signifikan',
                        'Kota', 'Satu Data Gempa']:
            self.assertIn(visible, body)

        for hidden in ['Gempa Sorong (SWI)', 'Gempa Nabire (NBPI)',
                       'Gempa Nganjuk (NGJ)', 'Focal Mechanism']:
            self.assertNotIn(hidden, body, f'{hidden} tidak boleh terlihat oleh Angkasa')

    def test_all_office_models_are_registered_on_the_gempa_site(self):
        """Semua 9 model terdaftar di site katalog (terlepas dari izin user)."""
        registered = set(gempa_admin_site._registry.keys())
        for model in CATALOG_MODELS:
            self.assertIn(model, registered)

    def test_catalog_models_are_not_registered_on_the_otp_admin(self):
        """Regresi: /admin/ (OTP) tidak boleh ikut kebagian model katalog."""
        registered = set(django_admin.site._registry.keys())
        for model in CATALOG_MODELS:
            self.assertNotIn(model, registered,
                             f'{model.__name__} muncul di admin.site (OTP)')

    def test_non_staff_user_is_refused(self):
        plain = User.objects.create_user('plain', password='pass12345')
        self.client.force_login(plain)
        resp = self.client.get('/gempa-admin/')
        self.assertEqual(resp.status_code, 302)   # dialihkan ke login admin


class CatalogTablesTest(TestCase):
    """Tabel harus terpisah dari milik app repository (dulu sama-sama 'gempas')."""

    def test_table_names_are_namespaced(self):
        for model in CATALOG_MODELS:
            self.assertTrue(model._meta.db_table.startswith('katalog_'),
                            f'{model.__name__} memakai tabel {model._meta.db_table}')

    def test_gempa_table_does_not_collide_with_repository(self):
        from repository.models import Gempa as RepositoryGempa
        self.assertNotEqual(Gempa._meta.db_table, RepositoryGempa._meta.db_table)


class OperatorGroupTest(TestCase):
    """Satu grup per kantor, izinnya sama dengan akun per-user di .188."""

    EXPECTED = {
        'Operator Angkasa': 17,
        'Operator PGR V':   16,
        'Operator Nabire':   8,
        'Operator Sorong':   8,
    }

    def test_all_office_groups_exist_with_expected_permissions(self):
        for name, count in self.EXPECTED.items():
            with self.subTest(group=name):
                group = Group.objects.get(name=name)
                self.assertEqual(group.permissions.count(), count)

    def test_every_group_only_holds_catalog_permissions(self):
        for name in self.EXPECTED:
            group = Group.objects.get(name=name)
            apps = {p.content_type.app_label for p in group.permissions.all()}
            self.assertEqual(apps, {'gempa'}, name)

    def test_legacy_single_group_is_gone(self):
        self.assertFalse(Group.objects.filter(name=LEGACY_GROUP_NAME).exists())

    def test_nabire_cannot_touch_the_jayapura_catalog(self):
        """Inti pemisahan kantor: Nabire hanya boleh mengubah tabelnya sendiri."""
        nabire = Group.objects.get(name='Operator Nabire')
        codenames = set(nabire.permissions.values_list('codename', flat=True))
        self.assertIn('change_gempanabire', codenames)
        self.assertIn('view_gempanabire', codenames)
        self.assertNotIn('view_gempa', codenames)
        self.assertNotIn('change_gempa', codenames)
        self.assertNotIn('delete_gempasorong', codenames)

    def test_sorong_scoped_to_its_own_catalog(self):
        sorong = Group.objects.get(name='Operator Sorong')
        codenames = set(sorong.permissions.values_list('codename', flat=True))
        self.assertIn('change_gempasorong', codenames)
        self.assertNotIn('change_gempanabire', codenames)
        self.assertNotIn('change_gempa', codenames)

    def test_angkasa_sees_balaigempa_but_only_view(self):
        angkasa = Group.objects.get(name='Operator Angkasa')
        codenames = set(angkasa.permissions.values_list('codename', flat=True))
        self.assertIn('view_balaigempa', codenames)
        self.assertNotIn('change_balaigempa', codenames)

    def test_sync_is_idempotent(self):
        before = {n: Group.objects.get(name=n).permissions.count()
                  for n in self.EXPECTED}
        ensure_operator_groups(sender=None)
        after = {n: Group.objects.get(name=n).permissions.count()
                 for n in self.EXPECTED}
        self.assertEqual(before, after)

    def test_declared_codenames_all_exist(self):
        """Kalau nama izin berubah, tes ini memberi tahu lebih awal."""
        from django.contrib.auth.models import Permission
        available = set(Permission.objects
                        .filter(content_type__app_label='gempa')
                        .values_list('codename', flat=True))
        for name, spec in OPERATOR_GROUPS.items():
            with self.subTest(group=name):
                self.assertEqual(set(spec['permissions']) - available, set())


class NotifyEndpointTest(TestCase):
    def test_unknown_model_returns_400(self):
        resp = self.client.get('/gempa-notify/latest/', {'model': 'tidak-ada'})
        self.assertEqual(resp.status_code, 400)

    def test_returns_latest_event_for_model(self):
        make_event(Gempa, event_id='ev-notify', magnitudo='5.2')
        resp = self.client.get('/gempa-notify/latest/', {'model': 'gempa'})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data['mag'], '5.2')
        self.assertEqual(data['ket'], 'uji')
        self.assertTrue(data['template_url'].startswith('/gempa-admin/'))

    def test_empty_model_returns_null_id(self):
        resp = self.client.get('/gempa-notify/latest/', {'model': 'gempa'})
        self.assertEqual(json.loads(resp.content), {'id': None})


class EarthquakesAPITest(TestCase):
    def test_returns_geojson_feature_collection(self):
        make_event(Balaigempa, event_id='ev-api', bujur='140.70', lintang='-2.50')
        resp = self.client.get('/api/earthquakes')
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.content)
        self.assertEqual(payload['type'], 'FeatureCollection')
        self.assertEqual(len(payload['features']), 1)
        feature = payload['features'][0]
        self.assertEqual(feature['properties']['id'], 'ev-api')
        self.assertEqual(feature['geometry']['coordinates'], [140.70, -2.50])
        self.assertEqual(feature['properties']['time'], '2026-10-01T10:00:00Z')

    def test_rows_without_event_id_are_skipped(self):
        make_event(Balaigempa, event_id=None)
        resp = self.client.get('/api/earthquakes')
        self.assertEqual(json.loads(resp.content)['features'], [])


class PostLoginRedirectTest(TestCase):
    """Setelah login, operator mendarat di katalog kantornya sendiri."""

    LANDINGS = {
        ANGKASA_GROUP:     '/gempa-admin/gempa/gempa/',
        'Operator PGR V':  '/gempa-admin/gempa/balaigempa/',
        'Operator Nabire': '/gempa-admin/gempa/gempanabire/',
        'Operator Sorong': '/gempa-admin/gempa/gempasorong/',
    }

    def test_each_office_lands_on_its_own_catalog(self):
        for group_name, expected in self.LANDINGS.items():
            with self.subTest(group=group_name):
                username = 'op-' + group_name.split()[-1].lower()
                user = User.objects.create_user(username, password='pass12345',
                                                is_staff=True)
                user.groups.add(Group.objects.get(name=group_name))
                self.client.force_login(user)

                resp = self.client.get(reverse('post_login'))
                self.assertEqual(resp.status_code, 302)
                self.assertEqual(resp['Location'], expected)
                # halaman tujuan memang boleh dibuka user itu
                self.assertEqual(self.client.get(expected).status_code, 200)
                self.client.logout()

    def test_angkasa_example_from_the_request(self):
        """Contoh yang diminta: angkasa -> /gempa-admin/gempa/gempa/."""
        user = User.objects.create_user('angkasa_op', password='pass12345',
                                        is_staff=True, email='angkasa@bmkg.go.id')
        user.groups.add(Group.objects.get(name=ANGKASA_GROUP))
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('post_login'))['Location'],
                         '/gempa-admin/gempa/gempa/')

    def test_other_users_keep_the_old_destination(self):
        user = User.objects.create_user('biasa', password='pass12345')
        self.client.force_login(user)

        resp = self.client.get(reverse('post_login'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/dashboard/')

    def test_superuser_is_not_hijacked(self):
        """Superuser tidak dipaksa ke admin katalog meski jadi anggotanya."""
        user = User.objects.create_superuser('root', password='pass12345')
        user.groups.add(Group.objects.get(name=ANGKASA_GROUP))
        self.client.force_login(user)

        resp = self.client.get(reverse('post_login'))
        self.assertEqual(resp['Location'], '/dashboard/')

    def test_every_office_declares_a_reversible_landing(self):
        from django.urls import reverse as rev
        for name, spec in OPERATOR_GROUPS.items():
            with self.subTest(group=name):
                self.assertIn('landing', spec)
                self.assertTrue(rev(spec['landing']).startswith('/gempa-admin/'))


class AccountsLoginRedirectTest(TestCase):
    """End-to-end lewat /accounts/login/ — halaman yang benar-benar dipakai user."""

    def test_operator_logging_in_by_email_lands_on_its_catalog(self):
        user = User.objects.create_user('angkasa', password='rahasiaku123',
                                        is_staff=True, email='angkasa@bmkg.go.id')
        user.groups.add(Group.objects.get(name=ANGKASA_GROUP))

        resp = self.client.post('/accounts/login/',
                                {'username': 'angkasa@bmkg.go.id',
                                 'password': 'rahasiaku123'},
                                follow=True)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.redirect_chain[-1][0], '/gempa-admin/gempa/gempa/')
        self.assertContains(resp, 'Gempa JAY')

    def test_nabire_operator_lands_on_the_nabire_catalog(self):
        user = User.objects.create_user('nabire', password='rahasiaku123',
                                        is_staff=True, email='nabire@bmkg.go.id')
        user.groups.add(Group.objects.get(name='Operator Nabire'))

        resp = self.client.post('/accounts/login/',
                                {'username': 'nabire@bmkg.go.id',
                                 'password': 'rahasiaku123'},
                                follow=True)
        self.assertEqual(resp.redirect_chain[-1][0], '/gempa-admin/gempa/gempanabire/')

    def test_explicit_next_url_is_respected(self):
        """Kalau ada ?next=, hormati itu — bukan halaman katalog."""
        user = User.objects.create_user('sorong_op', password='rahasiaku123',
                                        is_staff=True, email='sorong@bmkg.go.id')
        user.groups.add(Group.objects.get(name='Operator Sorong'))

        resp = self.client.post('/accounts/login/?next=/logbook/', {
            'username': 'sorong@bmkg.go.id',
            'password': 'rahasiaku123',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/logbook/')

    def test_ordinary_user_still_goes_to_dashboard(self):
        User.objects.create_user('pegawai', password='rahasiaku123',
                                 email='pegawai@bmkg.go.id')
        resp = self.client.post('/accounts/login/', {
            'username': 'pegawai@bmkg.go.id',
            'password': 'rahasiaku123',
        }, follow=True)
        # dilewatkan dispatcher, tapi berakhir tetap di dashboard
        self.assertEqual(resp.redirect_chain[-1][0], '/dashboard/')
        self.assertNotIn('/gempa-admin/', str(resp.redirect_chain))
        self.assertEqual(resp.status_code, 200)


class AdminSubPageTest(TestCase):
    """Halaman custom di dalam admin (press / template / SMS / info)."""

    def setUp(self):
        self.staff = User.objects.create_user('subop', password='pass12345',
                                             is_staff=True)
        self.staff.groups.add(Group.objects.get(name=ANGKASA_GROUP))
        self.client.force_login(self.staff)
        self.gempa = make_event(Gempa, event_id='ev-sub')
        self.balai = make_event(Balaigempa, event_id='ev-balai')
        self.sorong = make_event(Gempasorong, event_id='ev-sorong')
        self.nabire = make_event(Gempanabire, event_id='ev-nabire')
        self.sig = Significant.objects.create(
            event_id='ev-sig', tanggal='2026-10-01', jam='10:00:00',
            lintang='-2.50', bujur='140.70', magnitudo='4.5', depth=10,
            lokasi='uji', dirasakan='-')

    def _url(self, model, pk, action):
        return f'/gempa-admin/gempa/{model._meta.model_name}/{pk}/{action}/'

    def test_read_only_sub_pages_render(self):
        pages = [
            (Gempa, self.gempa.pk, 'press'),
            (Gempa, self.gempa.pk, 'template-balai'),
            (Balaigempa, self.balai.pk, 'sms'),
            (Balaigempa, self.balai.pk, 'press'),
            (Gempasorong, self.sorong.pk, 'info'),
            (Gempanabire, self.nabire.pk, 'info'),
            (Significant, self.sig.pk, 'template'),
        ]
        for model, pk, action in pages:
            with self.subTest(action=action, model=model.__name__):
                resp = self.client.get(self._url(model, pk, action))
                self.assertEqual(resp.status_code, 200)

    def test_inject_is_refused_for_other_users(self):
        """inject_view hanya untuk user 'angkasa' (perilaku .188)."""
        for model, pk in [(Balaigempa, self.balai.pk), (Gempasorong, self.sorong.pk)]:
            with self.subTest(model=model.__name__):
                resp = self.client.get(self._url(model, pk, 'inject'))
                self.assertEqual(resp.status_code, 302)
        # dan tidak ada baris baru yang tersalin ke tabel JAY
        self.assertEqual(Gempa.objects.count(), 1)

    def test_kirim_sdg_copies_row_into_satu_data(self):
        before = Satudatagempa.objects.count()
        resp = self.client.get(self._url(Gempa, self.gempa.pk, 'kirim-sdg'))
        self.assertEqual(resp.status_code, 302)          # redirect ke changelist
        self.assertEqual(Satudatagempa.objects.count(), before + 1)
        created = Satudatagempa.objects.latest('id')
        self.assertEqual(created.sumber, 'BMKG-JAY')


class ImportOperatorsCommandTest(TestCase):
    """Akun operator dari .188: hash password dipakai apa adanya, grup per kantor."""

    def _fixture(self, accounts):
        import json
        import tempfile
        fd, path = tempfile.mkstemp(suffix='.json')
        with open(fd, 'w') as fh:
            json.dump(accounts, fh)
        self.addCleanup(os.unlink, path)
        return path

    def _account(self, username, password='rahasia123', **extra):
        from django.contrib.auth.hashers import make_password
        data = {
            'username': username,
            'password': make_password(password),   # hash asli dari .188
            'email': f'{username}@bmkg.go.id',
            'first_name': username.capitalize(),
            'last_name': '',
            'is_active': True,
            'is_staff': True,
            'is_superuser': False,
            'date_joined': '2024-05-09T01:10:00+00:00',
            'last_login': None,
            'permissions': [],
        }
        data.update(extra)
        return data

    def test_imported_operator_keeps_its_password(self):
        """Bukti utama: operator bisa login pakai password .188-nya."""
        path = self._fixture([self._account('nabire')])
        call_command('import_operators', path, verbosity=0)

        user = User.objects.get(username='nabire')
        self.assertTrue(user.check_password('rahasia123'))
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertEqual(user.email, 'nabire@bmkg.go.id')
        self.assertEqual(list(user.groups.values_list('name', flat=True)),
                         ['Operator Nabire'])

    def test_superuser_flag_is_never_imported(self):
        path = self._fixture([self._account('sorong', is_superuser=True)])
        call_command('import_operators', path, verbosity=0)
        self.assertFalse(User.objects.get(username='sorong').is_superuser)

    def test_angkasa_collision_frees_the_username_without_deleting_history(self):
        old = User.objects.create_user('angkasa', password='lama-sekali')
        old_pk = old.pk

        path = self._fixture([self._account('angkasa')])
        call_command('import_operators', path, verbosity=0)

        # akun lama TIDAK dihapus, hanya diparkir
        parked = User.objects.get(pk=old_pk)
        self.assertEqual(parked.username, 'angkasa_lama')
        self.assertFalse(parked.is_active)

        # username kini milik akun .188, dengan password .188
        new = User.objects.get(username='angkasa')
        self.assertNotEqual(new.pk, old_pk)
        self.assertTrue(new.check_password('rahasia123'))
        self.assertEqual(list(new.groups.values_list('name', flat=True)),
                         ['Operator Angkasa'])

    def test_reimport_is_idempotent(self):
        path = self._fixture([self._account('pgr5')])
        call_command('import_operators', path, verbosity=0)
        first_pk = User.objects.get(username='pgr5').pk
        call_command('import_operators', path, verbosity=0)
        user = User.objects.get(username='pgr5')
        self.assertEqual(user.pk, first_pk)          # diperbarui, bukan diduplikasi
        self.assertEqual(User.objects.filter(username='pgr5').count(), 1)

    def test_dry_run_changes_nothing(self):
        path = self._fixture([self._account('nabire')])
        call_command('import_operators', path, '--dry-run', verbosity=0)
        self.assertFalse(User.objects.filter(username='nabire').exists())


class EmailLoginTest(TestCase):
    """Operator .188 login dengan ALAMAT EMAIL (bukan username).

    Halaman /gempa-admin/login/ berlabel "Email:" dan memakai input type=email,
    jadi backend EmailOrUsernameBackend wajib aktif — tanpa itu login dengan
    angkasa@bmkg.go.id ditolak walaupun passwordnya benar.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            'angkasa', password='rahasiaku123', is_staff=True,
            email='angkasa@bmkg.go.id')
        self.user.groups.add(Group.objects.get(name=ANGKASA_GROUP))

    def test_authenticate_with_email(self):
        from django.contrib.auth import authenticate
        user = authenticate(username='angkasa@bmkg.go.id', password='rahasiaku123')
        self.assertIsNotNone(user)
        self.assertEqual(user.pk, self.user.pk)

    def test_authenticate_with_email_is_case_insensitive(self):
        from django.contrib.auth import authenticate
        user = authenticate(username='ANGKASA@BMKG.GO.ID', password='rahasiaku123')
        self.assertIsNotNone(user)

    def test_authenticate_with_username_still_works(self):
        from django.contrib.auth import authenticate
        self.assertIsNotNone(
            authenticate(username='angkasa', password='rahasiaku123'))

    def test_wrong_password_is_rejected(self):
        from django.contrib.auth import authenticate
        self.assertIsNone(
            authenticate(username='angkasa@bmkg.go.id', password='salah'))

    def test_blank_username_is_rejected(self):
        """10 dari 17 user .189 beremail kosong — jangan sampai cocok semua."""
        from django.contrib.auth import authenticate
        self.assertIsNone(authenticate(username='', password='rahasiaku123'))

    def test_unknown_email_is_rejected(self):
        from django.contrib.auth import authenticate
        self.assertIsNone(
            authenticate(username='tidak@ada.go.id', password='rahasiaku123'))

    def test_real_login_form_accepts_the_email(self):
        """End-to-end: POST ke halaman login katalog pakai email -> 302."""
        resp = self.client.post(
            '/gempa-admin/login/?next=/gempa-admin/',
            {'username': 'angkasa@bmkg.go.id', 'password': 'rahasiaku123'},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/gempa-admin/')

    def test_non_staff_email_cannot_enter_the_admin(self):
        User.objects.create_user('bukanstaf', password='rahasiaku123',
                                is_staff=False, email='bukanstaf@bmkg.go.id')
        resp = self.client.post(
            '/gempa-admin/login/?next=/gempa-admin/',
            {'username': 'bukanstaf@bmkg.go.id', 'password': 'rahasiaku123'},
        )
        self.assertEqual(resp.status_code, 200)      # form ditolak, bukan redirect

    def test_inactive_user_is_rejected(self):
        from django.contrib.auth import authenticate
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        self.assertIsNone(
            authenticate(username='angkasa@bmkg.go.id', password='rahasiaku123'))


class GempaStaticAssetsTest(TestCase):
    """Regresi: setiap {% static %} di template gempa harus benar-benar ada.

    Kerusakan yang dicegah: template hasil port memakai aset dari .188
    (css/js/images/gjson) yang tidak ikut tercopy, sehingga halaman
    template-balai penuh 404 dan peta gagal render ('png is not defined').
    """

    #: Aset yang dipinjam dari .188 dan wajib ada.
    REQUIRED_ASSETS = [
        'css/L.Icon.Pulse.css',
        'js/L.Icon.Pulse.js',
        'images/earthquake.png',
        'images/header-balai-sep-2024.png',
        'gjson/png.js',
        'gjson/batasinapng.js',
        'gjson/indofaults.js',
        'gjson/patahan.js',
        'gjson/plates.js',
        'gjson/subduksi.js',
    ]

    def test_borrowed_assets_are_present(self):
        for ref in self.REQUIRED_ASSETS:
            with self.subTest(asset=ref):
                self.assertIsNotNone(finders.find(ref), f'aset hilang: {ref}')

    def test_every_static_tag_in_gempa_templates_resolves(self):
        """Kalau ada {% static 'x' %} yang filenya tidak ada, tes ini gagal."""
        base = pathlib.Path(settings.BASE_DIR) / 'gempa' / 'templates'
        missing = {}
        for tpl in base.rglob('*.html'):
            text = tpl.read_text(errors='replace')
            for ref in re.findall(r"{%\s*static\s+['\"]([^'\"]+)['\"]", text):
                # {% static '/x' %} tetap benar saat dirender (Django membuang
                # garis miring depan), tapi finders.find() menolaknya.
                if finders.find(ref.lstrip('/')) is None:
                    missing.setdefault(ref, set()).add(str(tpl.relative_to(base)))
        self.assertEqual(missing, {}, f'static tidak ditemukan: {missing}')

    def test_gjson_files_define_the_variables_the_templates_use(self):
        """template-balai memakai variabel 'png', 'worldPlates', dst dari gjson."""
        expected = {
            'gjson/png.js': 'var png',
            'gjson/plates.js': 'var worldPlates',
            'gjson/patahan.js': 'var',
            'gjson/subduksi.js': 'var',
        }
        for ref, needle in expected.items():
            with self.subTest(asset=ref):
                found = finders.find(ref)
                head = pathlib.Path(found).read_text(errors='replace')[:200]
                self.assertIn(needle, head)

    def test_port_note_is_not_printed_on_the_admin_page(self):
        """Komentar multi-baris {# #} dulu ikut tercetak ke halaman."""
        staff = User.objects.create_user('staticcheck', password='pass12345',
                                         is_staff=True)
        staff.groups.add(Group.objects.get(name='Operator Angkasa'))
        self.client.force_login(staff)

        body = self.client.get('/gempa-admin/gempa/gempa/').content.decode()
        self.assertNotIn('tidak ikut diport', body)
        self.assertNotIn('/laporan-bulanan/', body)

    def test_no_multiline_hash_comments_in_gempa_templates(self):
        """{#' #} Django hanya berlaku satu baris — multi-baris bocor ke halaman."""
        base = pathlib.Path(settings.BASE_DIR) / 'gempa' / 'templates'
        offenders = []
        for tpl in base.rglob('*.html'):
            text = tpl.read_text(errors='replace')
            if re.search(r'\{#[^\n#]*\n[^\n]*#\}', text):
                offenders.append(str(tpl.relative_to(base)))
        self.assertEqual(offenders, [])


# ── Peta GMT (port dari buat_peta.sh .188) ───────────────────────────────────
import shutil
import subprocess
import tempfile
from unittest import mock

from django.test import override_settings

from gempa import gmt
from gempa.signals import gmt_generation_suspended


class GmtMapTest(TestCase):
    """Kontrak argumen + perilaku generator peta."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.work = self.tmp / 'jay'
        self.out = self.tmp / 'uploads'
        self.work.mkdir()
        self.out.mkdir()
        self.script = self.work / 'buat_peta.sh'
        self.script.write_text('#!/bin/bash\nexit 0\n')
        over = override_settings(GMT_ENABLED=True,
                                 GMT_UPLOADS_DIR=str(self.out),
                                 GMT_WORKDIR=str(self.work))
        over.enable()
        self.addCleanup(over.disable)

    def _expected(self, name):
        return self.out / name

    def test_filename_contract_matches_what_the_templates_look_for(self):
        """gmt_image() mencari PREFIX_YYYY-MM-DD_HHMMSSUTC.png."""
        self.assertEqual(gmt.map_filename('jay', '2026-10-02', '19:34:47'),
                         'JAY_2026-10-02_193447UTC.png')
        self.assertEqual(gmt.map_filename('balai', '2026-10-02', '19:34:47'),
                         'PGR5_2026-10-02_193447UTC.png')
        self.assertEqual(gmt.map_filename('nabire', '2026-10-02', '193447'),
                         'NBPI_2026-10-02_193447UTC.png')
        self.assertEqual(gmt.map_filename('sorong', '2026-10-02', '19:34:47'),
                         'SWI_2026-10-02_193447UTC.png')

    def test_generate_passes_the_exact_arguments_of_the_original_script(self):
        expected = self._expected('JAY_2026-10-02_193447UTC.png')

        def fake_run(cmd, **kwargs):
            expected.write_bytes(b'png')
            return subprocess.CompletedProcess(cmd, 0, stdout='ok', stderr='')

        with mock.patch('gempa.gmt.subprocess.run', side_effect=fake_run) as run:
            result = gmt.generate('jay', lat='-4.89', lon='134.04', mag='3.5',
                                 tanggal='2026-10-02', origin='19:34:47', depth=91)

        self.assertTrue(result.created)
        self.assertEqual(result.filename, 'JAY_2026-10-02_193447UTC.png')

        cmd = run.call_args.args[0]
        self.assertEqual(cmd[0], 'bash')
        self.assertEqual(cmd[1], str(self.script))
        self.assertEqual(cmd[2:], ['-4.89', '134.04', '3.5', '2026-10-02', '193447', '91'])

        env = run.call_args.kwargs['env']
        self.assertEqual(env['GMT_UPLOADS_DIR'], str(self.out))
        self.assertEqual(env['GMT_WORKDIR'], str(self.work))
        self.assertEqual(env['GMT_HISTORI'], str(self.tmp / 'jay' / 'histori_gmt.gmt'))

    def test_existing_map_is_skipped_unless_forced(self):
        (self.out / 'JAY_2026-10-02_193447UTC.png').write_bytes(b'png')
        with mock.patch('gempa.gmt.subprocess.run') as run:
            result = gmt.generate('jay', lat='-4.89', lon='134.04', mag='3.5',
                                  tanggal='2026-10-02', origin='19:34:47', depth=91)
        self.assertTrue(result.skipped)
        run.assert_not_called()

    def test_force_regenerates(self):
        (self.out / 'JAY_2026-10-02_193447UTC.png').write_bytes(b'png')
        with mock.patch('gempa.gmt.subprocess.run') as run:
            run.return_value = subprocess.CompletedProcess([], 0, stdout='', stderr='')
            result = gmt.generate('jay', lat='-4.89', lon='134.04', mag='3.5',
                                  tanggal='2026-10-02', origin='19:34:47', depth=91,
                                  force=True)
        self.assertEqual(run.call_count, 1)
        self.assertTrue(result.skipped or result.created)   # berkas dianggap ada -> skip aman

    def test_failed_script_raises(self):
        with mock.patch('gempa.gmt.subprocess.run') as run:
            run.return_value = subprocess.CompletedProcess([], 1, stdout='', stderr='GMT ERROR')
            with self.assertRaises(gmt.GmtError) as ctx:
                gmt.generate('jay', lat='-4.89', lon='134.04', mag='3.5',
                             tanggal='2026-10-02', origin='19:34:47', depth=91)
        self.assertIn('GMT ERROR', str(ctx.exception))

    def test_success_without_output_file_raises(self):
        with mock.patch('gempa.gmt.subprocess.run') as run:
            run.return_value = subprocess.CompletedProcess([], 0, stdout='ok', stderr='')
            with self.assertRaises(gmt.GmtError):
                gmt.generate('jay', lat='-4.89', lon='134.04', mag='3.5',
                             tanggal='2026-10-02', origin='19:34:47', depth=91)

    def test_invalid_inputs_are_rejected(self):
        cases = [
            dict(region='nganjuk'),                       # tidak ada script di .188
            dict(tanggal='2 Oktober 2026'),
            dict(origin='19:34'),                          # kurang detik
            dict(lat='-4.89; rm -rf /'),                   # argumen masuk shell!
            dict(lon='abc'),
            dict(mag=''),
            dict(depth='dangkal'),
        ]
        base = dict(region='jay', lat='-4.89', lon='134.04', mag='3.5',
                    tanggal='2026-10-02', origin='19:34:47', depth=91)
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(gmt.GmtError):
                    gmt.generate(**{**base, **case})

    @override_settings(GMT_ENABLED=False)
    def test_disabled_setting_skips_everything(self):
        with mock.patch('gempa.gmt.subprocess.run') as run:
            result = gmt.generate('jay', lat='-4.89', lon='134.04', mag='3.5',
                                  tanggal='2026-10-02', origin='19:34:47', depth=91)
        self.assertTrue(result.skipped)
        run.assert_not_called()


class GmtSignalTest(TestCase):
    """Event baru otomatis menjadwalkan pembuatan peta."""

    def setUp(self):
        over = override_settings(GMT_ENABLED=True)
        over.enable()
        self.addCleanup(over.disable)

    def test_new_event_queues_the_task(self):
        with mock.patch('gempa.tasks.generate_gmt_map_task.delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                obj = make_event(Gempa)
        self.assertEqual(delay.call_count, 1)
        self.assertEqual(delay.call_args.args, ('jay', obj.pk))

    def test_region_mapping_per_model(self):
        for model, region in ((Gempa, 'jay'), (Balaigempa, 'balai'),
                              (Gempasorong, 'sorong'), (Gempanabire, 'nabire')):
            with self.subTest(model=model.__name__):
                with mock.patch('gempa.tasks.generate_gmt_map_task.delay') as delay:
                    with self.captureOnCommitCallbacks(execute=True):
                        obj = make_event(model, event_id=f'ev-{region}')
                self.assertEqual(delay.call_args.args, (region, obj.pk))

    def test_incomplete_event_does_not_queue(self):
        with mock.patch('gempa.tasks.generate_gmt_map_task.delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                make_event(Gempa, origin='')          # tanpa origin
        delay.assert_not_called()

    def test_suspended_context_prevents_queueing(self):
        """load_katalog membungkus loaddata: 113k event tidak boleh render peta."""
        with mock.patch('gempa.tasks.generate_gmt_map_task.delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                with gmt_generation_suspended():
                    make_event(Gempa)
        delay.assert_not_called()

    def test_update_does_not_queue(self):
        obj = make_event(Gempa)
        with mock.patch('gempa.tasks.generate_gmt_map_task.delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                obj.ket = 'diubah'
                obj.save()
        delay.assert_not_called()

    def test_bulk_create_does_not_queue(self):
        """loaddata/bulk tidak memicu signal — jaring pengaman kedua."""
        with mock.patch('gempa.tasks.generate_gmt_map_task.delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                Gempa.objects.bulk_create([Gempa(
                    event_id='ev-bulk', tanggal=datetime.date(2026, 10, 2),
                    origin='10:00:00', lintang='-2.5', bujur='140.7',
                    magnitudo='4.5', depth=10, ket='bulk')])
        delay.assert_not_called()

    def test_broker_failure_does_not_break_the_save(self):
        with mock.patch('gempa.tasks.generate_gmt_map_task.delay',
                        side_effect=RuntimeError('redis mati')):
            with self.captureOnCommitCallbacks(execute=True):
                obj = make_event(Gempa, event_id='ev-broker')
        self.assertTrue(Gempa.objects.filter(pk=obj.pk).exists())


class GmtAdminButtonTest(TestCase):
    """Tombol 'Buat Peta GMT' di halaman press/template."""

    def setUp(self):
        self.staff = User.objects.create_user('gmtop', password='pass12345',
                                              is_staff=True)
        self.staff.groups.add(Group.objects.get(name=ANGKASA_GROUP))
        self.client.force_login(self.staff)
        self.event = make_event(Gempa, event_id='ev-gmt')

    def test_template_page_offers_the_button(self):
        url = reverse('gempa_admin:gempa-template-balai', args=[self.event.pk])
        body = self.client.get(url).content.decode()
        self.assertIn('/buat-peta/', body)
        self.assertIn('Buat Peta GMT', body)

    def test_post_generates_the_map(self):
        url = reverse('gempa_admin:gempa-buat-peta', args=[self.event.pk])
        with mock.patch('gempa.admin.gmt.generate') as generate:
            generate.return_value = gmt.GmtResult(created=True, seconds=4.2,
                                                  filename='JAY_x.png')
            resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(generate.called)
        kwargs = generate.call_args.kwargs
        self.assertEqual(generate.call_args.args[0], 'jay')
        self.assertTrue(kwargs['force'])            # tombol selalu menyegarkan
        self.assertEqual(kwargs['origin'], self.event.origin)

    def test_get_is_refused(self):
        url = reverse('gempa_admin:gempa-buat-peta', args=[self.event.pk])
        with mock.patch('gempa.admin.gmt.generate') as generate:
            resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        generate.assert_not_called()

    def test_gmt_error_is_reported_not_raised(self):
        url = reverse('gempa_admin:gempa-buat-peta', args=[self.event.pk])
        with mock.patch('gempa.admin.gmt.generate',
                        side_effect=gmt.GmtError('script meledak')):
            resp = self.client.post(url, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Gagal membuat peta GMT')

    def test_every_map_admin_knows_its_region(self):
        expected = {'GempaAdmin': 'jay', 'BalaigempaAdmin': 'balai',
                    'GempasorongAdmin': 'sorong', 'GempanahireAdmin': 'nabire',
                    'SignificantAdmin': 'jay'}
        for model, adm in gempa_admin_site._registry.items():
            name = type(adm).__name__
            if name in expected:
                with self.subTest(admin=name):
                    self.assertEqual(adm.gmt_region, expected[name])

    def test_significant_maps_its_text_date_to_the_file_name(self):
        adm = gempa_admin_site._registry[Significant]
        sig = Significant.objects.create(event_id='ev-sig-gmt', tanggal='02-Okt-26',
                                         jam='19:34:47', lintang='-2.5',
                                         bujur='140.7', magnitudo='4.5', depth=10)
        tanggal, origin = adm.gmt_event_args(sig)
        self.assertEqual(tanggal, '2026-10-02')
        self.assertEqual(origin, '19:34:47')


# ── Ingest event SeisComp (pengganti insertgempa.php .188) ───────────────────
from django.test import Client as _Client

from gempa.seiscomp import INGEST_REGIONS, SeiscompError, ingest, parse_bulletin

#: Contoh isi `scbulletin -E <id> -3` (mailexportfile.txt).
BULLETIN = """Date            2026-10-02
Time            19:34:47
Latitude        -4.8900   0.5   -4.89
Longitude       134.0400  0.7   134.04
Depth           91
Magnitude       ML 3.5
preferred       3.5  0.2  ML
Public ID       20261002193447.000000
Residual        0.47  0.0  1.2
"""


class SeiscompParseTest(TestCase):
    """Parser harus sama dengan _parse_seiscomp.py di .188."""

    def test_parses_a_real_bulletin_layout(self):
        data = parse_bulletin(BULLETIN)
        self.assertEqual(data['tanggal'], '2026-10-02')
        self.assertEqual(data['origin'], '19:34:47')
        self.assertEqual(data['lintang'], '-4.8900')
        self.assertEqual(data['bujur'], '134.0400')
        self.assertEqual(data['magnitudo'], 3.5)
        self.assertEqual(data['depth'], 91)
        self.assertEqual(data['event_id'], '20261002193447.000000')

    def test_handles_conservative_crlf_and_blank_lines(self):
        data = parse_bulletin(BULLETIN.replace('\n', '\r\n') + '\n\n')
        self.assertEqual(data['event_id'], '20261002193447.000000')

    def test_second_call_without_time_is_ignored(self):
        data = parse_bulletin(BULLETIN)
        self.assertEqual(data['origin'], '19:34:47')

    def test_odd_optional_line_does_not_break_the_parse(self):
        """Satu baris pendek/aneh tidak boleh menggagalkan seluruh bulletin."""
        data = parse_bulletin('Residual        0.47\n' + BULLETIN)
        self.assertEqual(data['event_id'], '20261002193447.000000')

    def test_unparseable_required_value_is_caught_by_ingest(self):
        """Nilai wajib yang rusak -> pesan 'kurang lengkap', bukan 500."""
        with self.assertRaises(SeiscompError) as ctx:
            ingest('jay', BULLETIN.replace('Depth           91', 'Depth           dalam'))
        self.assertIn('kurang lengkap', str(ctx.exception))
        self.assertIn('depth', str(ctx.exception))


class SeiscompIngestTest(TestCase):
    """Penyimpanan: idempoten, ket & delta terisi."""

    def test_first_ingest_inserts(self):
        result = ingest('jay', BULLETIN)
        self.assertEqual(result['action'], 'inserted')
        self.assertEqual(result['model'], 'Gempa')
        self.assertEqual(result['event_id'], '20261002193447.000000')
        obj = Gempa.objects.get(event_id=result['event_id'])
        self.assertEqual(str(obj.tanggal), '2026-10-02')
        self.assertEqual(str(obj.origin), '19:34:47')
        self.assertEqual(str(obj.magnitudo), '3.5')
        self.assertEqual(obj.depth, 91)
        self.assertEqual(obj.sumber, 'angkasa')      # extra khusus region jay
        self.assertNotEqual(result['ket'], '')        # nearest city terhitung

    def test_second_ingest_updates_without_duplicating(self):
        first = ingest('jay', BULLETIN)
        changed = BULLETIN.replace('preferred       3.5', 'preferred       4.1')
        second = ingest('jay', changed)
        self.assertEqual(second['action'], 'updated')
        self.assertEqual(second['pk'], first['pk'])
        self.assertEqual(Gempa.objects.filter(event_id=first['event_id']).count(), 1)
        self.assertEqual(str(Gempa.objects.get(pk=first['pk']).magnitudo), '4.1')

    def test_created_at_is_preserved_on_update(self):
        """Waktu sebar pertama tidak boleh tertimpa sinkronisasi."""
        first = ingest('jay', BULLETIN)
        before = Gempa.objects.get(pk=first['pk']).created_at
        ingest('jay', BULLETIN.replace('preferred       3.5', 'preferred       4.2'))
        self.assertEqual(Gempa.objects.get(pk=first['pk']).created_at, before)

    def test_region_maps_to_the_right_model(self):
        expected = {'jay': 'Gempa', 'balai': 'Balaigempa', 'nabire': 'Gempanabire',
                    'sorong': 'Gempasorong', 'nganjuk': 'Gempanganjuk'}
        self.assertEqual(INGEST_REGIONS, expected)

    def test_incomplete_bulletin_is_rejected(self):
        with self.assertRaises(SeiscompError) as ctx:
            ingest('jay', 'Date            2026-10-02\nTime            19:34:47\n')
        self.assertIn('kurang lengkap', str(ctx.exception))

    def test_unknown_region_is_rejected(self):
        with self.assertRaises(SeiscompError):
            ingest('bandung', BULLETIN)


@override_settings(SEISCOMP_INGEST_TOKEN='tok-rahasia-123')
class SeiscompIngestApiTest(TestCase):
    """Endpoint POST /api/gempa/ingest/<region>/."""

    URL = '/api/gempa/ingest/jay/'

    def _post(self, body=BULLETIN, token='tok-rahasia-123', url=None,
              content_type='text/plain'):
        headers = {}
        if token is not None:
            headers['HTTP_AUTHORIZATION'] = f'Bearer {token}'
        return self.client.post(url or self.URL, data=body,
                                content_type=content_type, **headers)

    def test_requires_a_token(self):
        self.assertEqual(self._post(token=None).status_code, 401)
        self.assertEqual(self._post(token='salah').status_code, 401)
        self.assertEqual(Gempa.objects.count(), 0)

    def test_accepts_the_raw_bulletin(self):
        resp = self._post()
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['action'], 'inserted')
        self.assertEqual(data['region'], 'jay')
        self.assertTrue(Gempa.objects.filter(event_id=data['event_id']).exists())

    def test_unknown_region_is_404(self):
        resp = self._post(url='/api/gempa/ingest/bandung/')
        self.assertEqual(resp.status_code, 404)
        self.assertIn('region', resp.json()['error'])

    def test_empty_body_is_400(self):
        self.assertEqual(self._post(body='   ').status_code, 400)

    def test_incomplete_body_is_400_with_reason(self):
        resp = self._post(body='Date            2026-10-02\n')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('kurang lengkap', resp.json()['error'])

    def test_repeat_delivery_is_idempotent(self):
        first = self._post().json()
        second = self._post().json()
        self.assertEqual(second['action'], 'updated')
        self.assertEqual(second['pk'], first['pk'])
        self.assertEqual(Gempa.objects.count(), 1)

    def test_new_event_queues_the_gmt_map(self):
        """Peta GMT otomatis dibuat untuk event baru (lihat gempa/signals.py)."""
        # GMT_ENABLED=False di dev (tidak ada /var/www/gmt), jadi dinyalakan khusus di sini.
        with override_settings(GMT_ENABLED=True):
            with mock.patch('gempa.tasks.generate_gmt_map_task.delay') as delay:
                with self.captureOnCommitCallbacks(execute=True):
                    resp = self._post()
        self.assertEqual(resp.json()['action'], 'inserted')
        self.assertEqual(delay.call_count, 1)
        self.assertEqual(delay.call_args.args[0], 'jay')

    def test_csrf_is_not_required_for_the_api(self):
        """Bukti csrf_exempt: klien yang menegakkan CSRF pun tetap diterima."""
        strict = _Client(enforce_csrf_checks=True)
        resp = strict.post(self.URL, data=BULLETIN, content_type='text/plain',
                           HTTP_AUTHORIZATION='Bearer tok-rahasia-123')
        self.assertEqual(resp.status_code, 200)

    def test_json_body_is_not_accepted_as_bulletin(self):
        """Klien salah format harus dapat pesan jelas, bukan 500."""
        resp = self._post(body='{"latitude": -4.89}')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('kurang lengkap', resp.json()['error'])

    def test_get_is_rejected(self):
        resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, 405)


# ── Tombol "Copy Info Gempa" + "Capture Peta" (WhatsApp) ─────────────────────
PETA_TEMPLATES = ['angkasatemplatebalai.html', 'angkasatemplatebalai_gfz.html',
                  'balaisms.html', 'sorongtemplatebalai.html',
                  'nabiretemplatebalai.html', 'significanttemplate.html']


class PetaWhatsappButtonsTest(TestCase):
    """Tombol salin-tempel untuk WhatsApp di halaman peta/press."""

    def _read(self, name):
        path = pathlib.Path(settings.BASE_DIR) / 'gempa' / 'templates' / 'gempa' / name
        self.assertTrue(path.exists(), f'{name} tidak ada')
        return path.read_text()

    def test_every_peta_page_has_the_info_line_and_both_buttons(self):
        for name in PETA_TEMPLATES:
            with self.subTest(template=name):
                html = self._read(name)
                self.assertIn('id="info-gempa"', html)
                self.assertIn('id="btn-copy-info"', html)
                self.assertIn('id="btn-capture-peta"', html)
                self.assertIn('data-target="info-gempa"', html)
                self.assertIn('data-target="streetmap-baru"', html)

    def test_each_page_names_its_own_seiscomp_code_in_the_download(self):
        expected = {
            'angkasatemplatebalai.html': 'peta-BMKG-JAY',
            'angkasatemplatebalai_gfz.html': 'peta-BMKG-JAY',
            'balaisms.html': 'peta-BMKG-PGR-V',
            'sorongtemplatebalai.html': 'peta-BMKG-SWI',
            'nabiretemplatebalai.html': 'peta-BMKG-NBPI',
            'significanttemplate.html': 'peta-BMKG-JAY',
        }
        for name, filename in expected.items():
            with self.subTest(template=name):
                self.assertIn(f'data-filename="{filename}"', self._read(name))

    def test_buttons_sit_OUTSIDE_the_captured_element(self):
        """Kalau tombolnya ikut terfoto, gambar yang dikirim ke WhatsApp jelek."""
        for name in PETA_TEMPLATES:
            with self.subTest(template=name):
                html = self._read(name)
                info_end = html.index('</strong></p>')
                streetmap_close = html.index('</div>', info_end)
                buttons = html.index('peta-actions')
                self.assertGreater(buttons, streetmap_close,
                                   'tombol harus setelah </div> penutup streetmap-baru')

    def test_pages_load_the_helper_and_html2canvas_lazily(self):
        for name in PETA_TEMPLATES:
            with self.subTest(template=name):
                html = self._read(name)
                self.assertIn("js/peta_copy_capture.js", html)
                self.assertIn('data-h2c-url="{% static \'js/html2canvas.min.js\' %}"', html)

    def test_helper_assets_exist_and_are_served(self):
        for rel in ('js/peta_copy_capture.js', 'js/html2canvas.min.js'):
            with self.subTest(asset=rel):
                path = pathlib.Path(settings.BASE_DIR) / 'gempa' / 'static' / rel
                self.assertTrue(path.exists(), f'{rel} tidak ada di app static')
                self.assertGreater(path.stat().st_size, 1000)
                self.assertIsNotNone(finders.find(rel), f'{rel} tidak ditemukan finders')

    def test_rendered_peta_page_shows_the_real_info_text_and_buttons(self):
        staff = User.objects.create_user('peta_probe', password='pass12345', is_staff=True)
        staff.groups.add(Group.objects.get(name='Operator Angkasa'))
        self.client.force_login(staff)
        event = make_event(Gempa, event_id='ev-peta-buttons')
        url = reverse('gempa_admin:gempa-template-balai', args=[event.pk])
        body = self.client.get(url).content.decode()

        self.assertIn('id="info-gempa"', body)
        self.assertIn('id="btn-copy-info"', body)
        self.assertIn('id="btn-capture-peta"', body)
        self.assertIn('::BMKG-JAY', body)                 # kode SeisComp di teksnya
        self.assertIn('/static/js/peta_copy_capture.js', body)
        self.assertIn('/static/js/html2canvas.min.js', body)
