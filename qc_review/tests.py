"""Tests for the daily station waveform-health feature (station QC)."""
import datetime
import os
import shutil
import tempfile

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.authtoken.models import Token

from . import station_rules as R
from .models import StationDailyQC, StationDiagnosis

DAY = datetime.date(2026, 10, 12)
URL = "/qc/api/station-daily/"


def good(**over):
    """Metrics of a healthy short-period channel."""
    m = {"availability_pct": 100.0, "n_gaps": 0, "n_overlaps": 0, "max_gap_s": 0.0,
         "timing_quality_mean": 100.0, "timing_quality_min": 100.0, "clock_locked_pct": 100.0,
         "noise_rms": 50.0, "flatline_pct": 0.0, "n_spikes": 5, "n_clip_runs": 0}
    m.update(over)
    return m


def zne(z=None, n=None, e=None, band="SH"):
    return [{"location": "", "channel": f"{band}Z", "metrics": z or good()},
            {"location": "", "channel": f"{band}N", "metrics": n or good()},
            {"location": "", "channel": f"{band}E", "metrics": e or good()}]


def codes(findings):
    return {(f.channel, f.code, f.severity) for f in findings}


class StationRulesTest(TestCase):
    def test_every_rule_code_has_an_indonesian_label(self):
        import inspect
        import re
        src = inspect.getsource(R)
        codes_in_rules = set(re.findall(r'add\("([A-Z_]+)"', src)) | set(re.findall(r'Finding\(\s*"([A-Z_]+)"', src))
        self.assertGreaterEqual(len(codes_in_rules), 11)
        self.assertEqual(codes_in_rules - set(R.CODE_LABELS_ID), set())

    def test_healthy_station_has_no_findings(self):
        self.assertEqual(R.evaluate(zne()), [])

    def test_dead_vertical_component(self):
        f = R.evaluate(zne(z=good(noise_rms=0.5)))
        self.assertIn(("SHZ", "COMPONENT_DEAD", "red"), codes(f))
        msg = next(x for x in f if x.code == "COMPONENT_DEAD")
        self.assertIn("vertikal", msg.message_id)
        self.assertIn("Vertical component", msg.message_en)

    def test_noisy_component(self):
        self.assertIn(("SHN", "COMPONENT_NOISY", "yellow"),
                      codes(R.evaluate(zne(n=good(noise_rms=5000)))))

    def test_no_data_and_gaps(self):
        f = codes(R.evaluate(zne(z=good(availability_pct=0.0),
                                 n=good(availability_pct=60.0, n_gaps=4, max_gap_s=9000),
                                 e=good(availability_pct=95.0, n_gaps=1, max_gap_s=100))))
        self.assertIn(("SHZ", "NO_DATA", "red"), f)
        self.assertIn(("SHN", "DATA_GAPS", "red"), f)
        self.assertIn(("SHE", "DATA_GAPS", "yellow"), f)

    def test_flatline(self):
        self.assertIn(("SHE", "FLATLINE", "red"),
                      codes(R.evaluate(zne(e=good(flatline_pct=100.0, noise_rms=0.0)))))

    def test_future_timestamp_is_time_shift(self):
        f = R.evaluate(zne(z=good(future_dates=["2036-02-07"])))
        hit = next(x for x in f if x.code == "FUTURE_TIMESTAMP")
        self.assertEqual(hit.severity, "red")
        self.assertIn("Pergeseran waktu", hit.message_id)
        self.assertIn("2036-02-07", hit.message_en)

    def test_low_timing_quality(self):
        self.assertIn(("SHZ", "TIMING_QUALITY", "red"),
                      codes(R.evaluate(zne(z=good(timing_quality_mean=10.0)))))

    def test_chronic_bad_timing_is_still_flagged(self):
        # SWPM: timing quality 10% every day must not become "normal".
        hist = {("", "SHZ"): [good(timing_quality_mean=10.0)] * 14}
        f = [x for x in R.evaluate(zne(z=good(timing_quality_mean=10.0)), hist)
             if x.code == "TIMING_QUALITY"]
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0].severity, "red")
        self.assertIn("berlangsung terus", f[0].message_id)
        self.assertIn("ongoing", f[0].message_en)

    def test_duration_format(self):
        self.assertEqual(R.fmt_duration(34), "34s")
        self.assertEqual(R.fmt_duration(173), "2m 53s")
        self.assertEqual(R.fmt_duration(4352), "1j 12m 32s")
        self.assertEqual(R.fmt_duration(4352, "en"), "1h 12m 32s")
        f = R.evaluate(zne(z=good(availability_pct=3.3, n_gaps=3, max_gap_s=80961)))
        gap = next(x for x in f if x.code == "DATA_GAPS")
        self.assertIn("terpanjang 22j 29m 21s", gap.message_id)
        self.assertIn("longest 22h 29m 21s", gap.message_en)

    def test_no_data_says_since_when(self):
        f = R.evaluate(zne(z=good(availability_pct=0.0, last_data_day="2026-09-19",
                                  days_without_data=22)))
        nd = next(x for x in f if x.code == "NO_DATA")
        self.assertIn("sejak 19-09-2026 (22 hari tanpa data)", nd.message_id)
        self.assertIn("since 19-09-2026 (22 days without data)", nd.message_en)

    def test_clock_unlocked_needs_baseline(self):
        today = zne(z=good(clock_locked_pct=0.0))
        self.assertNotIn("CLOCK_UNLOCKED", {x.code for x in R.evaluate(today)})
        hist = {("", "SHZ"): [good()] * 7}
        self.assertIn(("SHZ", "CLOCK_UNLOCKED", "red"), codes(R.evaluate(today, hist)))
        # Digitizers that never set the lock bit stay quiet.
        hist0 = {("", "SHZ"): [good(clock_locked_pct=0.0)] * 7}
        self.assertNotIn("CLOCK_UNLOCKED", {x.code for x in R.evaluate(today, hist0)})

    def test_amplitude_change_vs_baseline(self):
        hist = {("", "SHZ"): [good(noise_rms=50.0)] * 7}
        self.assertIn(("SHZ", "AMPLITUDE_CHANGE", "yellow"),
                      codes(R.evaluate(zne(z=good(noise_rms=800.0), n=good(noise_rms=800.0),
                                           e=good(noise_rms=800.0)), hist)))

    def test_spikes_only_against_baseline(self):
        today = zne(z=good(n_spikes=3000))
        self.assertNotIn("SPIKES", {x.code for x in R.evaluate(today)})
        hist = {("", "SHZ"): [good(n_spikes=2500)] * 7}
        self.assertNotIn("SPIKES", {x.code for x in R.evaluate(today, hist)})
        # A one-day burst (e.g. an earthquake) is not flagged ...
        hist = {("", "SHZ"): [good(n_spikes=20)] * 7}
        self.assertNotIn("SPIKES", {x.code for x in R.evaluate(today, hist)})
        # ... but two elevated days in a row are.
        hist = {("", "SHZ"): [good(n_spikes=20)] * 7 + [good(n_spikes=2000)]}
        self.assertIn(("SHZ", "SPIKES", "yellow"), codes(R.evaluate(today, hist)))

    def test_flatline_is_not_reported_as_clipping(self):
        f = {x.code for x in R.evaluate(zne(e=good(flatline_pct=100.0, n_clip_runs=1, noise_rms=0.0)))}
        self.assertIn("FLATLINE", f)
        self.assertNotIn("CLIPPING", f)

    def test_worst(self):
        self.assertEqual(R.worst([]), "green")
        self.assertEqual(R.worst(["yellow", "green", "red"]), "red")


class StationDailyApiTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("qcworker", password="x")
        self.token = Token.objects.create(user=self.user)

    def post(self, body, token=True):
        kw = {"HTTP_AUTHORIZATION": f"Token {self.token.key}"} if token else {}
        return self.client.post(URL, body, content_type="application/json", **kw)

    def batch(self, day=DAY, channels=None, station="RKPI"):
        return {"day": day.isoformat(),
                "stations": [{"network": "IA", "station": station, "channels": channels or zne()}]}

    def test_requires_token(self):
        self.assertIn(self.post(self.batch(), token=False).status_code, (401, 403))
        self.assertEqual(StationDailyQC.objects.count(), 0)

    def test_rejects_bad_payload(self):
        self.assertEqual(self.post({"stations": []}).status_code, 400)

    def test_ingest_stores_rows_and_diagnoses(self):
        r = self.post(self.batch(channels=zne(e=good(flatline_pct=100.0, noise_rms=0.0))))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["channels"], 3)
        self.assertEqual(StationDailyQC.objects.count(), 3)
        self.assertEqual(StationDailyQC.objects.get(channel="SHE").status, "red")
        self.assertEqual(StationDailyQC.objects.get(channel="SHZ").status, "green")
        d = StationDiagnosis.objects.get()
        self.assertEqual((d.channel, d.code), ("SHE", "FLATLINE"))
        self.assertTrue(d.message_id and d.message_en)

    def test_reingest_replaces_the_day(self):
        self.post(self.batch(channels=zne(e=good(flatline_pct=100.0, noise_rms=0.0))))
        self.post(self.batch())
        self.assertEqual(StationDailyQC.objects.count(), 3)
        self.assertEqual(StationDiagnosis.objects.count(), 0)
        self.assertEqual(set(StationDailyQC.objects.values_list("status", flat=True)), {"green"})

    def test_history_is_used_for_baseline_rules(self):
        for i in range(7, 0, -1):
            self.post(self.batch(day=DAY - datetime.timedelta(days=i)))
        self.post(self.batch(channels=zne(z=good(clock_locked_pct=0.0))))
        self.assertTrue(StationDiagnosis.objects.filter(day=DAY, code="CLOCK_UNLOCKED",
                                                        channel="SHZ").exists())


class SilentStationTest(TestCase):
    """A station that stops sending must stay in the report as 'no data since'."""

    def setUp(self):
        user = User.objects.create_user("qcworker", password="x")
        self.auth = {"HTTP_AUTHORIZATION": f"Token {Token.objects.create(user=user).key}"}

    def post(self, day, stations, complete=True):
        return self.client.post(URL, {"day": day.isoformat(), "complete": complete, "stations": [
            {"network": "IA", "station": s, "channels": zne()} for s in stations]},
            content_type="application/json", **self.auth)

    def silent_for_three_days(self):
        """MBPI sends until DAY-3, then only JAY is in the daily batches."""
        for i in range(5, -1, -1):
            self.post(DAY - datetime.timedelta(days=i), ["JAY", "MBPI"] if i >= 3 else ["JAY"])

    def test_missing_station_is_added_as_no_data(self):
        self.silent_for_three_days()
        rows = StationDailyQC.objects.filter(station="MBPI", day=DAY)
        self.assertEqual(rows.count(), 3)
        self.assertEqual(set(rows.values_list("status", flat=True)), {"red"})
        d = StationDiagnosis.objects.filter(station="MBPI", day=DAY, code="NO_DATA").first()
        last = (DAY - datetime.timedelta(days=3)).strftime('%d-%m-%Y')
        self.assertIn(f"sejak {last} (3 hari tanpa data)", d.message_id)

    def test_partial_batch_does_not_invent_missing_stations(self):
        self.post(DAY - datetime.timedelta(days=1), ["JAY", "MBPI"])
        self.post(DAY, ["JAY"], complete=False)
        self.assertFalse(StationDailyQC.objects.filter(station="MBPI", day=DAY).exists())

    def test_reevaluate_command_applies_current_rules(self):
        from django.core.management import call_command
        for i in range(3, -1, -1):
            self.post(DAY - datetime.timedelta(days=i), ["JAY", "MBPI"] if i else ["JAY"])
        StationDiagnosis.objects.all().delete()
        call_command("reevaluate_station_qc", stdout=open(os.devnull, "w"))
        self.assertTrue(StationDiagnosis.objects.filter(station="MBPI", day=DAY, code="NO_DATA").exists())

    def test_caption_names_silent_station_with_date(self):
        from . import station_report
        self.silent_for_three_days()
        cap = station_report.build_caption(station_report.report_data(DAY))
        self.assertIn(f"IA.MBPI: Tidak ada data sejak {(DAY - datetime.timedelta(days=3)).strftime('%d-%m')}", cap)


class StationHealthPagesTest(TestCase):
    def setUp(self):
        user = User.objects.create_user("qcworker", password="x")
        token = Token.objects.create(user=user)
        body = {"day": DAY.isoformat(), "stations": [
            {"network": "IA", "station": "ARMI", "channels": zne(z=good(noise_rms=0.5))},
            {"network": "IA", "station": "JAY", "channels": zne(band="BH")}]}
        self.client.post(URL, body, content_type="application/json",
                         HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_empty_page(self):
        StationDailyQC.objects.all().delete()
        r = self.client.get("/qc/stations/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Belum ada data QC stasiun")

    def test_grid_and_findings_in_both_languages(self):
        r = self.client.get("/qc/stations/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "IA.ARMI")
        self.assertContains(r, "IA.JAY")
        self.assertContains(r, "Komponen vertikal (SHZ) kemungkinan rusak")
        self.assertContains(r, "Vertical component (SHZ) likely broken")
        self.assertEqual(r.context["counts"], {"red": 1, "green": 1})

    def test_station_detail(self):
        r = self.client.get("/qc/stations/IA.ARMI/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "likely broken")
        self.assertEqual([c["channel"] for c in r.context["channels"]], ["SHZ", "SHN", "SHE"])
        self.assertEqual(self.client.get("/qc/stations/IA.NOPE/").status_code, 404)


class StationReportTest(TestCase):
    def setUp(self):
        user = User.objects.create_user("qcworker", password="x")
        token = Token.objects.create(user=user)
        body = {"day": DAY.isoformat(), "stations": [
            {"network": "IA", "station": "ARMI", "channels": zne(z=good(noise_rms=0.5))},
            {"network": "IA", "station": "SWPM", "channels": zne(z=good(timing_quality_mean=10.0))},
            {"network": "IA", "station": "JAY", "channels": zne(band="BH")}]}
        self.client.post(URL, body, content_type="application/json",
                         HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_pdf_is_built(self):
        from . import station_report
        pdf = station_report.build_pdf(DAY)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 2000)

    def test_caption_lists_red_stations(self):
        from . import station_report
        cap = station_report.build_caption(station_report.report_data(DAY))
        self.assertIn("🔴 2", cap)
        self.assertIn("IA.ARMI: Komponen rusak (SHZ)", cap)
        self.assertIn("IA.SWPM: Timing GPS buruk (SHZ)", cap)
        self.assertLessEqual(len(cap), 1024)

    def test_send_posts_pdf_to_telegram(self):
        from unittest import mock
        from django.test import override_settings
        from . import station_report
        with override_settings(TELEGRAM_BOT_TOKEN="T", TELEGRAM_CHAT_ID="-100",
                               STATION_QC_TELEGRAM_CHAT_ID=""), \
                mock.patch("theme.telegram.requests.post") as post:
            post.return_value.status_code = 200
            self.assertTrue(station_report.send_daily_report(DAY))
        url = post.call_args.args[0]
        self.assertTrue(url.endswith("/sendDocument"))
        self.assertEqual(post.call_args.kwargs["data"]["chat_id"], "-100")
        name, content, mime = post.call_args.kwargs["files"]["document"]
        self.assertEqual(name, f"kesehatan-stasiun-{DAY.isoformat()}.pdf")
        self.assertTrue(content.startswith(b"%PDF"))

    def test_missing_day_sends_warning_instead(self):
        from unittest import mock
        from django.test import override_settings
        from . import station_report
        with override_settings(TELEGRAM_BOT_TOKEN="T", TELEGRAM_CHAT_ID="-100",
                               STATION_QC_TELEGRAM_CHAT_ID="-200"), \
                mock.patch("theme.telegram.requests.post") as post:
            post.return_value.status_code = 200
            station_report.send_daily_report(DAY - datetime.timedelta(days=3))
        self.assertTrue(post.call_args.args[0].endswith("/sendMessage"))
        self.assertEqual(post.call_args.kwargs["data"]["chat_id"], "-200")
        self.assertIn("belum masuk", post.call_args.kwargs["data"]["text"])

    def test_command_writes_pdf(self):
        import os
        import tempfile
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "r.pdf")
            call_command("send_station_qc_report", day=DAY.isoformat(), out=out)
            with open(out, "rb") as fh:
                self.assertTrue(fh.read(4) == b"%PDF")


class StationReportGroupingTest(TestCase):
    def test_same_rule_on_three_components_is_one_row(self):
        from . import station_report
        user = User.objects.create_user("qcworker", password="x")
        token = Token.objects.create(user=user)
        gap = dict(availability_pct=50.0, n_gaps=2, max_gap_s=40000)
        self.client.post(URL, {"day": DAY.isoformat(), "stations": [
            {"network": "AU", "station": "MANU", "channels": zne(z=good(**gap), n=good(**gap),
                                                                e=good(**gap), band="BH")}]},
            content_type="application/json", HTTP_AUTHORIZATION=f"Token {token.key}")
        rows = station_report.report_data(DAY)["finding_rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["channels"], "BHZ, BHN, BHE")
        self.assertIn("BHZ/BHN/BHE", rows[0]["message_en"])

    def test_merged_message_drops_single_component_name(self):
        from . import station_report
        user = User.objects.create_user("qcworker", password="x")
        token = Token.objects.create(user=user)
        off = dict(availability_pct=0.0)
        self.client.post(URL, {"day": DAY.isoformat(), "stations": [
            {"network": "IA", "station": "AMPM", "channels": zne(z=good(**off), n=good(**off), e=good(**off))}]},
            content_type="application/json", HTTP_AUTHORIZATION=f"Token {token.key}")
        row = station_report.report_data(DAY)["finding_rows"][0]
        self.assertTrue(row["message_en"].startswith("No data on channel SHZ/SHN/SHE for the whole day."))
        self.assertTrue(row["message_id"].startswith("Tidak ada data pada kanal SHZ/SHN/SHE sepanjang hari."))


class StationReportRetryTest(TestCase):
    """Late data: one warning, then the report once the data arrives — never twice."""

    def setUp(self):
        from unittest import mock
        from django.test import override_settings
        user = User.objects.create_user("qcworker", password="x")
        self.auth = {"HTTP_AUTHORIZATION": f"Token {Token.objects.create(user=user).key}"}
        ov = override_settings(TELEGRAM_BOT_TOKEN="T", TELEGRAM_CHAT_ID="-100",
                               STATION_QC_TELEGRAM_CHAT_ID="")
        ov.enable()
        self.addCleanup(ov.disable)
        p = mock.patch("theme.telegram.requests.post")
        self.post = p.start()
        self.addCleanup(p.stop)
        self.post.return_value.status_code = 200

    def deliver(self):
        self.client.post(URL, {"day": DAY.isoformat(), "stations": [
            {"network": "IA", "station": "JAY", "channels": zne()}]},
            content_type="application/json", **self.auth)

    def sent(self):
        return [c.args[0].rsplit("/", 1)[1] for c in self.post.call_args_list]

    def test_late_data_flow(self):
        from . import station_report
        from .models import StationQCReport
        station_report.send_daily_report(DAY)                 # 02:30: no data -> warning
        station_report.send_daily_report(DAY, retry=True)     # 04:30: still none -> quiet
        self.assertEqual(self.sent(), ["sendMessage"])
        self.assertIn("13:30 WIB", self.post.call_args.kwargs["data"]["text"])
        self.assertEqual(StationQCReport.objects.get(day=DAY).status, "warned")

        self.deliver()
        station_report.send_daily_report(DAY, retry=True)     # 06:30: data -> report
        self.assertEqual(self.sent(), ["sendMessage", "sendDocument"])
        self.assertIn("terlambat", self.post.call_args.kwargs["data"]["caption"])
        self.assertEqual(StationQCReport.objects.get(day=DAY).status, "sent")

        station_report.send_daily_report(DAY, retry=True)     # nothing more
        station_report.send_daily_report(DAY)
        self.assertEqual(len(self.sent()), 2)

    def test_on_time_report_is_not_repeated_by_retries(self):
        from . import station_report
        self.deliver()
        station_report.send_daily_report(DAY)
        station_report.send_daily_report(DAY, retry=True)
        station_report.send_daily_report(DAY, retry=True)
        self.assertEqual(self.sent(), ["sendDocument"])
        self.assertNotIn("terlambat", self.post.call_args.kwargs["data"]["caption"])

    def test_failed_send_is_retried(self):
        from . import station_report
        self.deliver()
        self.post.return_value.status_code = 500
        self.assertFalse(station_report.send_daily_report(DAY))
        self.post.return_value.status_code = 200
        self.assertTrue(station_report.send_daily_report(DAY, retry=True))
        self.assertEqual(self.sent(), ["sendDocument", "sendDocument"])

    def test_manual_command_always_resends(self):
        from django.core.management import call_command
        from . import station_report
        self.deliver()
        station_report.send_daily_report(DAY)
        call_command("send_station_qc_report", day=DAY.isoformat(), stdout=open(os.devnull, "w"))
        self.assertEqual(self.sent(), ["sendDocument", "sendDocument"])


class OnDutyResolverTest(TestCase):
    """on_duty_resolver (satu query) harus sama hasilnya dengan get_on_duty_staff."""

    def test_matches_get_on_duty_staff_including_overnight(self):
        import datetime as _d
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from jadwal.models import JadwalHarian, Pegawai, PolaDinas
        from .utils import WIT, get_on_duty_staff, on_duty_resolver
        pagi = PolaDinas.objects.create(kode="P", nama="Pagi", jam_mulai=_d.time(7), jam_selesai=_d.time(14), durasi=7)
        malam = PolaDinas.objects.create(kode="M", nama="Malam", jam_mulai=_d.time(21), jam_selesai=_d.time(7), durasi=10)
        a = Pegawai.objects.create(nama="A", nip="1", pangkat="-", jabatan="-")
        b = Pegawai.objects.create(nama="B", nip="2", pangkat="-", jabatan="-")
        JadwalHarian.objects.create(pegawai=a, tanggal=_d.date(2026, 3, 1), pola=pagi)
        JadwalHarian.objects.create(pegawai=b, tanggal=_d.date(2026, 3, 1), pola=malam)
        times = [_d.datetime(2026, 3, 1, h, 30, tzinfo=WIT) for h in (8, 13, 22)] + \
                [_d.datetime(2026, 3, 2, 3, 0, tzinfo=WIT), _d.datetime(2026, 3, 2, 9, 0, tzinfo=WIT)]
        times = [t.astimezone(_d.timezone.utc) for t in times]
        with CaptureQueriesContext(connection) as q:
            resolve = on_duty_resolver(times)
            got = [[d["pegawai"].nama for d in resolve(t)] for t in times]
        self.assertEqual(len(q.captured_queries), 1)
        expected = [[d["pegawai"].nama for d in get_on_duty_staff(t)] for t in times]
        self.assertEqual(got, expected)
        self.assertEqual(got, [["A"], ["A"], ["B"], ["B"], []])


class EventPetugasTest(TestCase):
    """Petugas jaga dilekatkan ke event QC sesuai jadwal dinas (mulai 2026)."""

    def setUp(self):
        import datetime as _d
        from jadwal.models import JadwalHarian, Pegawai, PolaDinas
        mt = PolaDinas.objects.create(kode="MT", nama="Malam", jam_mulai=_d.time(19, 30), jam_selesai=_d.time(8), durasi=12.5)
        ps = PolaDinas.objects.create(kode="PS", nama="Pagi Siang", jam_mulai=_d.time(7, 30), jam_selesai=_d.time(20), durasi=12.5)
        self.a = Pegawai.objects.create(nama="A", nip="1", pangkat="-", jabatan="-")
        self.b = Pegawai.objects.create(nama="B", nip="2", pangkat="-", jabatan="-")
        self.c = Pegawai.objects.create(nama="C", nip="3", pangkat="-", jabatan="-")
        JadwalHarian.objects.create(pegawai=self.a, tanggal=_d.date(2026, 1, 4), pola=mt)
        JadwalHarian.objects.create(pegawai=self.b, tanggal=_d.date(2026, 1, 4), pola=mt)
        JadwalHarian.objects.create(pegawai=self.c, tanggal=_d.date(2026, 1, 5), pola=ps)

    def _event(self, pid, wit):
        import datetime as _d
        from .utils import WIT
        from .models import Event
        return Event.objects.create(public_id=pid, origin_time=wit.replace(tzinfo=WIT).astimezone(_d.timezone.utc),
                                    latitude=-2.5, longitude=140.7, depth_km=10, magnitude=4.0)

    def test_command_assigns_by_schedule_and_skips_before_2026(self):
        import datetime as _d, io
        from django.core.management import call_command
        night = self._event("jay2026a", _d.datetime(2026, 1, 5, 2, 0))     # MT A+B
        day = self._event("jay2026b", _d.datetime(2026, 1, 5, 10, 0))      # PS C
        old = self._event("jay2025z", _d.datetime(2025, 12, 31, 22, 0))
        call_command("assign_qc_petugas", stdout=io.StringIO())
        self.assertEqual(set(night.petugas.all()), {self.a, self.b})
        self.assertEqual(list(day.petugas.all()), [self.c])
        self.assertFalse(old.petugas.exists())


class HandoverRuleTest(TestCase):
    """Jam irisan dikreditkan ke dinas sebelumnya; R/WFA ikut dihitung."""

    def test_handover_and_regular(self):
        import datetime as _d
        from jadwal.duty import staff_on_duty_at
        from jadwal.models import JadwalHarian, Pegawai, PolaDinas
        P = PolaDinas.objects.create
        mt = P(kode="MT", nama="Malam", jam_mulai=_d.time(19, 30), jam_selesai=_d.time(8), durasi=12.5)
        ps = P(kode="PS", nama="Pagi Siang", jam_mulai=_d.time(7, 30), jam_selesai=_d.time(20), durasi=12.5)
        r = P(kode="R", nama="Reguler", jam_mulai=_d.time(7, 30), jam_selesai=_d.time(16), durasi=7.5)
        psm = P(kode="PSM", nama="PSM", jam_mulai=_d.time(7, 30), jam_selesai=_d.time(8), durasi=24.5)
        peg = {n: Pegawai.objects.create(nama=n, nip=n, pangkat="-", jabatan="-") for n in ("MALAM", "PAGI", "REG", "MALAM2", "PSM")}
        J = JadwalHarian.objects.create
        J(pegawai=peg["MALAM"], tanggal=_d.date(2026, 1, 4), pola=mt)
        J(pegawai=peg["PAGI"], tanggal=_d.date(2026, 1, 5), pola=ps)
        J(pegawai=peg["REG"], tanggal=_d.date(2026, 1, 5), pola=r)
        J(pegawai=peg["MALAM2"], tanggal=_d.date(2026, 1, 5), pola=mt)
        J(pegawai=peg["PSM"], tanggal=_d.date(2026, 1, 5), pola=psm)
        t = lambda h, m=0: _d.datetime(2026, 1, 5, h, m)
        names = lambda x: sorted(p.nama for p in x)
        on = staff_on_duty_at([t(7, 45), t(10), t(15, 30), t(19, 45), t(23)])
        self.assertEqual(names(on[t(7, 45)]), ["MALAM"])                  # serah terima pagi -> dinas malam
        self.assertEqual(names(on[t(10)]), ["PAGI", "PSM", "REG"])        # mulai bersamaan dihitung bersama
        self.assertEqual(names(on[t(15, 30)]), ["PAGI", "PSM", "REG"])    # R sampai 16:00 (bukan 07:30+7,5)
        self.assertEqual(names(on[t(19, 45)]), ["PAGI", "PSM"])           # serah terima sore -> PS (PSM masih jalan)
        self.assertEqual(names(on[t(23)]), ["MALAM2", "PSM"])


class SilentRosterWorkerTest(TestCase):
    """station_qc.py lists every bound or archived station, even when silent for months."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import importlib.util
        path = os.path.join(settings.BASE_DIR, "scripts", "station_qc", "station_qc.py")
        spec = importlib.util.spec_from_file_location("station_qc_worker", path)
        cls.w = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.w)

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sds-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.archive = os.path.join(self.root, "var", "lib", "archive")
        self.keys = os.path.join(self.root, "etc", "key")
        os.makedirs(self.keys)

    def touch(self, net, sta, cha, day, loc=""):
        doy = day.timetuple().tm_yday
        d = os.path.join(self.archive, str(day.year), net, sta, f"{cha}.D")
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, f"{net}.{sta}.{loc}.{cha}.D.{day.year}.{doy:03d}"), "w").close()

    def key(self, net, sta, profile):
        with open(os.path.join(self.keys, f"station_{net}_{sta}"), "w") as fh:
            fh.write(f"# Binding references\nglobal:{profile}\nseedlink:x\n")

    def silent(self, expected=None):
        return self.w.silent_stations(self.archive, self.keys, DAY, expected or {})

    def test_long_silent_station_keeps_its_last_data_day(self):
        last = DAY - datetime.timedelta(days=200)
        for c in ("SHZ", "SHN", "SHE"):
            self.touch("IA", "WWPI", c, last)
        rows = self.silent()[("IA", "WWPI")]
        self.assertEqual(sorted(r[1] for r in rows), ["SHE", "SHN", "SHZ"])
        self.assertEqual(rows[0][2]["last_data_day"], last.isoformat())
        self.assertEqual(rows[0][2]["days_without_data"], 200)

    def test_bound_station_never_archived_uses_binding_stream(self):
        self.key("II", "KWJN", "00BH")
        rows = self.silent()[("II", "KWJN")]
        self.assertEqual({(r[0], r[1]) for r in rows}, {("00", "BHZ"), ("00", "BHN"), ("00", "BHE")})
        self.assertTrue(rows[0][2]["never_archived"])

    def test_retired_channel_on_live_station_is_not_listed(self):
        self.touch("IA", "JAY", "BHZ", DAY - datetime.timedelta(days=300))
        self.assertNotIn(("IA", "JAY"), self.silent({("IA", "JAY"): {("", "SHZ")}}))

    def test_retired_channel_on_silent_station_is_not_listed(self):
        self.touch("IA", "OLD", "SHZ", DAY - datetime.timedelta(days=50))
        self.touch("IA", "OLD", "BHZ", DAY - datetime.timedelta(days=300))
        self.assertEqual([r[1] for r in self.silent()[("IA", "OLD")]], ["SHZ"])

    def test_future_clock_files_do_not_count_as_data(self):
        self.touch("IA", "OBMI", "SHZ", DAY - datetime.timedelta(days=100))
        self.touch("IA", "OBMI", "SHZ", datetime.date(2036, 2, 7))
        self.assertEqual(self.silent()[("IA", "OBMI")][0][2]["days_without_data"], 100)


class SilentRosterIngestTest(TestCase):
    def setUp(self):
        user = User.objects.create_user("qcworker", password="x")
        self.auth = {"HTTP_AUTHORIZATION": f"Token {Token.objects.create(user=user).key}"}

    def post_silent(self, sta, metrics):
        return self.client.post(URL, {"day": DAY.isoformat(), "complete": True, "stations": [
            {"network": "IA", "station": sta, "channels": [
                {"location": "", "channel": c, "metrics": metrics} for c in ("SHZ", "SHN", "SHE")]}]},
            content_type="application/json", **self.auth)

    def test_worker_date_shown_without_history_on_this_server(self):
        self.post_silent("WWPI", {"availability_pct": 0.0, "last_data_day": "2026-01-20", "days_without_data": 200})
        d = StationDiagnosis.objects.get(station="WWPI", channel="SHZ", code="NO_DATA")
        self.assertIn("sejak 20-01-2026 (200 hari tanpa data)", d.message_id)
        self.assertEqual(self.client.get("/qc/stations/").status_code, 200)

    def test_never_archived_message(self):
        self.post_silent("ERPI", {"availability_pct": 0.0, "never_archived": True})
        d = StationDiagnosis.objects.get(station="ERPI", channel="SHZ", code="NO_DATA")
        self.assertIn("belum pernah masuk arsip", d.message_id)

    def test_caption_counts_long_silent_stations_and_keeps_recent_ones(self):
        from . import station_report
        for i in range(40):
            self.post_silent(f"DEAD{i}", {"availability_pct": 0.0, "last_data_day": "2026-01-20", "days_without_data": 200})
        self.post_silent("FRESH", {"availability_pct": 0.0, "last_data_day": "2026-10-01", "days_without_data": 5})
        cap = station_report.build_caption(station_report.report_data(DAY))
        self.assertIn("40 stasiun mati lebih dari 30 hari", cap)
        self.assertIn("IA.FRESH", cap)
        self.assertNotIn("DEAD1", cap)
        self.assertLessEqual(len(cap), 1024)

