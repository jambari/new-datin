from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class PengaduanListAccessTest(TestCase):
    def test_list_requires_login(self):
        resp = self.client.get(reverse("pengaduan_list"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp["Location"])

    def test_staff_can_open_list(self):
        self.client.force_login(User.objects.create_user("petugas", password="x"))
        self.assertEqual(self.client.get(reverse("pengaduan_list")).status_code, 200)

    def test_public_form_stays_open(self):
        self.assertEqual(self.client.get(reverse("pengaduan_form")).status_code, 200)
