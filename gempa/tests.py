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
