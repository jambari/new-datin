import datetime
import io
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from openpyxl import Workbook
from PIL import Image

from kualitas_udara.models import KAHSeriesData, SPMSeriesData
from lightning.models import DailyStrikeSummary, Strike
from magnet.models import KIndexDaily, MagneticObservation
from repository.models import EventResponseSpectrum, ShakemapEvent, Station

UTC = datetime.timezone.utc


def fake_tile(z, x, y):
    return Image.new("RGB", (256, 256), (200, 220, 240))


def report_url(jenis, start=(1, 2026), end=(3, 2026), **extra):
    params = {"jenis": jenis, "start_bulan": start[0], "start_tahun": start[1], "end_bulan": end[0],
              "end_tahun": end[1], "nip": "199202062012101001",
              "unit_kerja": "Stasiun Geofisika Jayapura", **extra}
    return "/reporting/laporan/?" + "&".join(f"{k}={v}" for k, v in params.items())


def kindex_workbook(sheet_year=2026):
    wb = Workbook()
    ws = wb.active
    ws.title = "Januari"
    ws["I2"], ws["J2"], ws["K2"] = "Bulan :", "Januari", sheet_year
    ws.append([])
    ws["A4"] = "DAY"
    for day in range(1, 32):
        row = 4 + day
        ws.cell(row, 1, day)
        if day == 20:
            ws.cell(row, 2, "Lost Data")
        else:
            ks = [8, 9, 4, 3, 2, 2, 1, 1] if day == 19 else [2, 3, 2, 1, 1, 2, 2, 3]
            for j, k in enumerate(ks):
                ws.cell(row, 2 + j, k)
            ws.cell(row, 10, 999 if day == 5 else None)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class ReportingTest(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("t", password="x", first_name="Jambari"))

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get("/reporting/").status_code, 302)
        self.assertEqual(self.client.get(report_url("kualitas_udara")).status_code, 302)

    def test_index_page(self):
        r = self.client.get("/reporting/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Laporan Bukti SKP")  # sidebar link
        self.assertContains(r, "Magnetbumi &amp; Listrik Udara")

    def test_invalid_period_redirects_with_message(self):
        r = self.client.get(report_url("kualitas_udara", start=(3, 2026), end=(1, 2026)), follow=True)
        self.assertContains(r, "Bulan akhir tidak boleh sebelum bulan awal")
        r = self.client.get(report_url("kualitas_udara", start=(1, 2025), end=(3, 2026)), follow=True)
        self.assertContains(r, "maksimal 12 bulan")

    def test_kualitas_udara_report(self):
        zeros = {f: 0.0 for f in ("ph", "dh", "ca", "mg", "na", "k", "nh4", "cl", "so4", "no3", "kt", "ac", "al", "ch", "ox")}
        KAHSeriesData.objects.create(stasiun="ANGKASAPURA", bulan="2026-01", minggu="05", **zeros)
        for i, ph in enumerate([4.5, 5.2, 4.9, 6.0], 1):
            KAHSeriesData.objects.create(stasiun="ANGKASAPURA", bulan="2026-02", minggu=f"0{i}", ph=ph, dh=8.0,
                                         ca=0.1, mg=0.1, na=0.4, cl=0.7, so4=0.3, kt=0.2, ac=10.0, ch=20.0)
        KAHSeriesData.objects.create(stasiun="ANGKASAPURA", bulan="2026-03", minggu="01", ph=7.3, dh=160.0,
                                     ca=5.0, mg=23.0, kt=28.0, ac=0.0)
        for d in (6, 12, 18, 30):
            SPMSeriesData.objects.create(stasiun="ANGKASAPURA", timestamp=datetime.date(2026, 1, d), spm=20.0 + d)
        r = self.client.get(report_url("kualitas_udara"))
        self.assertEqual(r.status_code, 200)
        c = r.context
        self.assertEqual(len(c["valid"]), 5)
        self.assertEqual(len(c["empty"]), 1)
        self.assertEqual(len(c["verify"]), 1)  # March outlier
        self.assertEqual(c["acid"], 3)
        self.assertEqual([d.day for d in c["spm_missing"]], [24])
        self.assertContains(r, "Tersedianya data Kualitas Udara yang berkualitas")
        self.assertContains(r, "199202062012101001")
        self.assertContains(r, "data:image/png;base64,")

    @mock.patch("reporting.osm._tile", side_effect=fake_tile)
    def test_magnet_petir_report(self, _tile):
        DailyStrikeSummary.objects.create(summary_date=datetime.date(2026, 1, 2), cg_plus_count=10,
                                          cg_minus_count=5, ic_count=3, total_count=18)
        for i in range(60):
            Strike.objects.create(epoch_ms=i, timestamp=datetime.datetime(2026, 1, 2, 3, i % 60, tzinfo=UTC),
                                  latitude=-2.3 - i * 0.005, longitude=140.5 + i * 0.005, strike_type=i % 3)
        for i in range(10):  # duplicate rows (same file ingested twice) count once
            Strike.objects.create(epoch_ms=i, timestamp=datetime.datetime(2026, 1, 2, 3, i % 60, tzinfo=UTC),
                                  latitude=-2.3 - i * 0.005, longitude=140.5 + i * 0.005, strike_type=i % 3)
        Strike.objects.create(epoch_ms=999, timestamp=datetime.datetime(2026, 1, 2, 4, 0, tzinfo=UTC),
                              latitude=-5.0, longitude=138.0, strike_type=0)  # outside the summary box
        MagneticObservation.objects.create(observation_date=datetime.date(2026, 3, 25), observer="Juan",
                                           session="Session 1", declination=2.79, inclination=-22.1,
                                           total_intensity=39263.08)
        MagneticObservation.objects.create(observation_date=datetime.date(2026, 1, 16), observer="Jambari",
                                           session="Session 1",
                                           deklinasi_readings={"WU": {"hh": "0", "mm": "47", "ss": "1", "circ": "303.5"}},
                                           inklinasi_readings={k: {"ftotal": "39273.0"} for k in ("NU", "SD", "ND", "SU")})
        self.client.post("/reporting/indeks-k/upload/",
                         {"berkas": SimpleUploadedFile("grafik_kindeks 2026.xlsx", kindex_workbook()), "tahun": 2026})
        r = self.client.get(report_url("magnet_petir"))
        self.assertEqual(r.status_code, 200)
        c = r.context
        self.assertEqual(c["petir_total"], 18)
        self.assertEqual(c["petir"][0]["map_points"], 60)
        self.assertIsNotNone(c["petir"][0]["map"])
        self.assertTrue(c["petir"][0]["map_mismatch"])  # 60 unique points vs 18 in the summary
        self.assertContains(r, "berbeda lebih dari 5%")
        self.assertEqual(len(c["magnet_reduced"]), 1)
        self.assertEqual(len(c["magnet_dim"]), 1)
        self.assertEqual(c["magnet_empty_months"], ["Februari 2026"])
        self.assertEqual(c["kdays"], 30)
        self.assertEqual([o.tanggal.day for o, _crit in c["k_storms"]], [19])
        self.assertContains(r, "OpenStreetMap")

    def test_kindex_import(self):
        r = self.client.post("/reporting/indeks-k/upload/",
                             {"berkas": SimpleUploadedFile("k.xlsx", kindex_workbook(sheet_year=2025)), "tahun": 2026},
                             follow=True)
        self.assertContains(r, "tahun di judul sheet 2025")
        self.assertContains(r, "30 hari berdata")
        lost = KIndexDaily.objects.get(tanggal=datetime.date(2026, 1, 20))
        self.assertFalse(lost.has_data)
        self.assertEqual(lost.keterangan, "Lost Data")
        storm = KIndexDaily.objects.get(tanggal=datetime.date(2026, 1, 19))
        self.assertEqual(storm.a_index, (240 + 400 + 27 + 15 + 7 + 7 + 3 + 3) / 8)
        self.assertEqual(storm.criteria, "Badai Menengah")
        self.assertEqual(KIndexDaily.objects.get(tanggal=datetime.date(2026, 1, 5)).a_index_source, 999)
        r = self.client.post("/reporting/indeks-k/upload/",
                             {"berkas": SimpleUploadedFile("k.txt", b"x"), "tahun": 2026}, follow=True)
        self.assertContains(r, "harus berformat .xlsx")

    def test_percepatan_tanah_report(self):
        Station.objects.create(code="JAY", network="IA", latitude=-2.51, longitude=140.70)
        Station.objects.create(code="SWI", network="IA", latitude=-2.60, longitude=140.30)
        ShakemapEvent.objects.create(event_id="20260114064812_32_-2600_140600_20260114064812", latitude=-2.6,
                                     longitude=140.6, magnitude=3.2, depth=10,
                                     event_time=datetime.datetime(2026, 1, 14, 6, 48, 12, tzinfo=UTC),
                                     location_string="10 km Jayapura")

        def spec(scale):
            return [{"T": 0.0, "Sa": 0.02 * scale}, {"T": 0.3, "Sa": 0.04 * scale},
                    {"T": 1.0, "Sa": 0.01 * scale}, {"T": 3.0, "Sa": 0.001 * scale}]
        for comp in ("HNE", "HNN", "HNZ"):
            EventResponseSpectrum.objects.create(event_id="20260114064812", station_code="JAY", component=comp, spectrum=spec(1))
            EventResponseSpectrum.objects.create(event_id="20260114064812", station_code="SWI", component=comp,
                                                 spectrum=spec(2000 if comp == "HNE" else 1))
        EventResponseSpectrum.objects.create(event_id="20260414000000", station_code="JAY", component="HNE", spectrum=spec(1))
        r = self.client.get(report_url("percepatan_tanah"))
        self.assertEqual(r.status_code, 200)
        c = r.context
        self.assertEqual(c["n_events"], 1)  # April event outside period
        self.assertEqual(c["n_records"], 6)
        self.assertEqual(c["n_bad"], 3)  # SWI spike + its siblings
        ev = c["events"][0]
        self.assertEqual(ev["nearest"]["station"], "JAY")
        self.assertAlmostEqual(ev["pga"]["pga"], 0.02)
        self.assertAlmostEqual(ev["sa03"]["sa03"], 0.04)
        self.assertContains(r, "nilai &gt; 3 g")


class OfficerIdentityTest(TestCase):
    def test_name_and_nip_come_from_logged_in_pegawai(self):
        from jadwal.models import Pegawai
        user = get_user_model().objects.create_user("jambari", password="x", first_name="Jambari")
        Pegawai.objects.create(user=user, nama="Jambari, S.Tr, M.Si", nip="199202062012101001",
                               pangkat="Penata", jabatan="PMG")
        self.client.force_login(user)
        index = self.client.get("/reporting/")
        self.assertContains(index, "Jambari, S.Tr, M.Si")
        self.assertNotContains(index, 'name="nama"')
        self.assertNotContains(index, "atasan")
        r = self.client.get(report_url("kualitas_udara", nip="000", nama="Orang Lain"))
        self.assertEqual(r.context["identity"]["nama"], "Jambari, S.Tr, M.Si")
        self.assertEqual(r.context["identity"]["nip"], "199202062012101001")
        self.assertNotContains(r, "Orang Lain")
        self.assertNotContains(r, "Mengetahui")

    def test_user_without_pegawai_uses_account_name_and_manual_nip(self):
        user = get_user_model().objects.create_user("tamu", password="x", first_name="Budi", last_name="Santoso")
        self.client.force_login(user)
        self.assertContains(self.client.get("/reporting/"), 'name="nip"')
        r = self.client.get(report_url("kualitas_udara", nip="123456"))
        self.assertEqual(r.context["identity"]["nama"], "Budi Santoso")
        self.assertEqual(r.context["identity"]["nip"], "123456")
