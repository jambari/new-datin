import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from .models import MagneticObservation, Precursor, MagnetDataAvailability


def make_observation(**kwargs):
    defaults = dict(
        observation_date=datetime.date(2024, 3, 1),
        observer='Jambari',
        session='Pagi',
    )
    defaults.update(kwargs)
    return MagneticObservation.objects.create(**defaults)


class MagneticObservationModelTest(TestCase):
    def test_create_and_str(self):
        obs = make_observation()
        self.assertIn('2024-03-01', str(obs))
        self.assertIn('Jambari', str(obs))

    def test_is_bartington_false_without_readings(self):
        obs = make_observation()
        self.assertFalse(obs.is_bartington)

    def test_is_bartington_true_with_deg_readings(self):
        obs = make_observation(deklinasi_readings={
            'WU': {'deg': 10, 'min': 30, 'sec': 0},
        })
        self.assertTrue(obs.is_bartington)

    def test_derived_components_calculated_on_save(self):
        obs = make_observation(
            declination=1.0,
            inclination=-30.0,
            total_intensity=45000.0,
        )
        obs.refresh_from_db()
        self.assertIsNotNone(obs.horizontal_intensity)
        self.assertIsNotNone(obs.vertical_intensity)
        self.assertIsNotNone(obs.north_component)
        self.assertIsNotNone(obs.east_component)

    def test_bartington_full_calculation(self):
        obs = make_observation(
            deklinasi_readings={
                'WU': {'deg': 181, 'min': 0, 'sec': 0},
                'ED': {'deg': 181, 'min': 0, 'sec': 0},
                'WD': {'deg': 181, 'min': 0, 'sec': 0},
                'EU': {'deg': 181, 'min': 0, 'sec': 0},
            },
            inklinasi_readings={
                'NU': {'deg': 150, 'min': 0, 'sec': 0, 'ftotal': 45000},
                'SD': {'deg': 300, 'min': 0, 'sec': 0, 'ftotal': 45000},
                'ND': {'deg': 210, 'min': 0, 'sec': 0, 'ftotal': 45000},
                'SU': {'deg': 60, 'min': 0, 'sec': 0, 'ftotal': 45000},
            },
        )
        obs.refresh_from_db()
        self.assertIsNotNone(obs.declination)
        self.assertIsNotNone(obs.inclination)
        self.assertEqual(float(obs.total_intensity), 45000.0)


class PrecursorModelTest(TestCase):
    def test_create_and_str(self):
        p = Precursor.objects.create(
            anomaly_timestamp=datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc),
            predicted_start_date=datetime.date(2024, 1, 10),
            predicted_end_date=datetime.date(2024, 1, 20),
            predicted_magnitude=6.0,
            location_description='Papua Tengah',
        )
        self.assertIn('Papua Tengah', str(p))

    def test_default_not_validated(self):
        p = Precursor.objects.create(
            anomaly_timestamp=datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc),
            predicted_start_date=datetime.date(2024, 1, 10),
            predicted_end_date=datetime.date(2024, 1, 20),
            predicted_magnitude=6.0,
            location_description='Test',
        )
        self.assertFalse(p.is_validated)


class MagnetDataAvailabilityModelTest(TestCase):
    def test_create_and_str(self):
        obj = MagnetDataAvailability.objects.create(
            station='JYP_P',
            date=datetime.date(2024, 3, 1),
            percentage=98.5,
        )
        self.assertIn('JYP_P', str(obj))

    def test_unique_together_constraint(self):
        MagnetDataAvailability.objects.create(
            station='JYP_P', date=datetime.date(2024, 3, 1), percentage=98.5
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            MagnetDataAvailability.objects.create(
                station='JYP_P', date=datetime.date(2024, 3, 1), percentage=50.0
            )


class MagnetViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('testuser', password='pass123')
        self.client.login(username='testuser', password='pass123')

    def test_observation_form_get(self):
        resp = self.client.get(reverse('observation_form'))
        self.assertEqual(resp.status_code, 200)

    def test_observation_bartington_form_get(self):
        resp = self.client.get(reverse('observation_bartington'))
        self.assertEqual(resp.status_code, 200)

    def test_observation_list_get(self):
        resp = self.client.get(reverse('observation_list'))
        self.assertEqual(resp.status_code, 200)

    def test_precursor_list_get(self):
        resp = self.client.get(reverse('precursor_list'))
        self.assertEqual(resp.status_code, 200)

    def test_magnet_availability_query_get(self):
        resp = self.client.get(reverse('magnet_availability_query'))
        self.assertEqual(resp.status_code, 200)

    def test_observation_detail_404_on_invalid(self):
        resp = self.client.get(reverse('observation_detail', args=[9999]))
        self.assertEqual(resp.status_code, 404)

    def test_precursor_detail_404_on_invalid(self):
        resp = self.client.get(reverse('precursor_detail', args=[9999]))
        self.assertEqual(resp.status_code, 404)

    def test_unauthenticated_redirects(self):
        self.client.logout()
        resp = self.client.get(reverse('observation_form'))
        self.assertIn(resp.status_code, [302, 403])

    def test_update_magnet_availability_post(self):
        payload = {'station': 'JYP_P', 'date': '2024-03-01', 'value': 99.0}
        resp = self.client.post(
            reverse('update_magnet_availability'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertIn(resp.status_code, [200, 201])


import json
