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

from django.contrib import admin as django_admin
from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from .apps import ensure_operator_group, KATALOG_GROUP_NAME
from .models import (Gempa, Balaigempa, Gempasorong, Gempanabire,
                     Satudatagempa, Gempanganjuk, Significant, City,
                     FocalMechanism)

CATALOG_MODELS = [Gempa, Balaigempa, Gempasorong, Gempanabire,
                  Satudatagempa, Gempanganjuk, Significant, City, FocalMechanism]


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
        self.staff.groups.add(Group.objects.get(name=KATALOG_GROUP_NAME))

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
        for model in CATALOG_MODELS:
            self.assertContains(resp, model._meta.verbose_name)
        # app lain di project ini tidak boleh muncul di sini
        for absent in ['Logbook', 'Repository', 'Jadwal', 'Perjadin', 'Tiket']:
            self.assertNotContains(resp, absent)

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
    def test_group_exists_with_all_catalog_permissions(self):
        group = Group.objects.get(name=KATALOG_GROUP_NAME)
        apps = {p.content_type.app_label for p in group.permissions.all()}
        self.assertEqual(apps, {'gempa'})
        # view/add/change/delete untuk 9 model
        self.assertEqual(group.permissions.count(), 36)

    def test_sync_is_idempotent(self):
        group = Group.objects.get(name=KATALOG_GROUP_NAME)
        before = group.permissions.count()
        ensure_operator_group(sender=None)
        self.assertEqual(group.permissions.count(), before)

    def test_group_member_can_delete_via_admin(self):
        """Izin delete harus benar-benar terpasang, bukan hanya view."""
        group = Group.objects.get(name=KATALOG_GROUP_NAME)
        codenames = set(group.permissions.values_list('codename', flat=True))
        self.assertIn('delete_gempa', codenames)
        self.assertIn('change_balaigempa', codenames)


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
    def test_catalog_group_member_lands_in_gempa_admin(self):
        user = User.objects.create_user('op2', password='pass12345', is_staff=True)
        user.groups.add(Group.objects.get(name=KATALOG_GROUP_NAME))
        self.client.force_login(user)

        resp = self.client.get(reverse('post_login'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], reverse('gempa_admin:index'))

    def test_other_users_keep_the_old_destination(self):
        user = User.objects.create_user('biasa', password='pass12345')
        self.client.force_login(user)

        resp = self.client.get(reverse('post_login'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/dashboard/')

    def test_superuser_is_not_hijacked(self):
        """Superuser tidak dipaksa ke admin katalog meski jadi anggotanya."""
        user = User.objects.create_superuser('root', password='pass12345')
        user.groups.add(Group.objects.get(name=KATALOG_GROUP_NAME))
        self.client.force_login(user)

        resp = self.client.get(reverse('post_login'))
        self.assertEqual(resp['Location'], '/dashboard/')


class AdminSubPageTest(TestCase):
    """Halaman custom di dalam admin (press / template / SMS / info)."""

    def setUp(self):
        self.staff = User.objects.create_user('subop', password='pass12345',
                                             is_staff=True)
        self.staff.groups.add(Group.objects.get(name=KATALOG_GROUP_NAME))
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
