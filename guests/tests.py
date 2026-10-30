from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Guest


class GuestDashboardAccessTest(TestCase):
    def setUp(self):
        self.guest = Guest.objects.create(nama="Tamu", dari="Uncen", keperluan="Kunjungan")

    def test_dashboard_requires_login(self):
        for url in (reverse("guests_dashboard_list"), reverse("guests_dashboard_delete", args=[self.guest.pk])):
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 302, url)
            self.assertIn("/accounts/login/", resp["Location"])

    def test_anonymous_cannot_delete(self):
        self.client.post(reverse("guests_dashboard_delete", args=[self.guest.pk]))
        self.assertTrue(Guest.objects.filter(pk=self.guest.pk).exists())

    def test_staff_can_open_dashboard(self):
        self.client.force_login(User.objects.create_user("petugas", password="x"))
        self.assertEqual(self.client.get(reverse("guests_dashboard_list")).status_code, 200)

    def test_public_guest_book_stays_open(self):
        self.assertEqual(self.client.get(reverse("guests_index")).status_code, 200)
