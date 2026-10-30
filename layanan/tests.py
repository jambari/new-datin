import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Layanan
from .notify import caption, send_permohonan


def _post_data(**extra):
    data = {
        "nama": "Budi <Santoso>", "instansi": "Universitas Cenderawasih", "alamat": "Jl. Raya Abepura",
        "email": "budi@example.com", "handphone": "+62 812-3456-7890", "jenis_data": "Peta Kegempaan",
        "surat": SimpleUploadedFile("Surat Permohonan.pdf", b"%PDF-1.4 isi", content_type="application/pdf"),
    }
    data.update(extra)
    return data


class FormulirPermohonanTest(TestCase):
    def setUp(self):
        self.private = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.private, ignore_errors=True)
        override = override_settings(PRIVATE_MEDIA_ROOT=self.private)
        override.enable()
        self.addCleanup(override.disable)
        self.url = reverse("layanan_formulir", kwargs={"id": 1})

    def test_get_shows_form(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="surat"')

    @mock.patch("layanan.views.queue_permohonan")
    def test_post_saves_permohonan_and_notifies(self, queue):
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(self.url, _post_data())
        self.assertRedirects(resp, self.url, fetch_redirect_response=False)
        obj = Layanan.objects.get()
        self.assertEqual(obj.status, "1")
        self.assertEqual(obj.instansi, "Universitas Cenderawasih")
        saved = Path(self.private) / obj.surat
        self.assertTrue(saved.is_file())
        self.assertTrue(saved.name.endswith("_Surat_Permohonan.pdf"))
        self.assertEqual(saved.read_bytes(), b"%PDF-1.4 isi")
        queue.assert_called_once_with(obj.pk)
        page = self.client.get(self.url)
        self.assertContains(page, f"nomor #{obj.pk}")

    @mock.patch("layanan.views.queue_permohonan")
    def test_rejects_bad_file_type(self, queue):
        data = _post_data(surat=SimpleUploadedFile("surat.exe", b"MZ", content_type="application/octet-stream"))
        resp = self.client.post(self.url, data)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Surat harus berupa PDF")
        self.assertContains(resp, 'value="Universitas Cenderawasih"')     # isian tidak hilang
        self.assertFalse(Layanan.objects.exists())
        queue.assert_not_called()

    @mock.patch("layanan.views.queue_permohonan")
    def test_rejects_invalid_email_and_missing_surat(self, queue):
        data = _post_data(email="bukan-email")
        data.pop("surat")
        resp = self.client.post(self.url, data)
        self.assertContains(resp, "Alamat email tidak valid.")
        self.assertContains(resp, "Surat permohonan wajib diunggah.")
        self.assertFalse(Layanan.objects.exists())

    @mock.patch("layanan.views.queue_permohonan")
    def test_honeypot_is_dropped(self, queue):
        resp = self.client.post(self.url, _post_data(website="http://spam.example"))
        self.assertRedirects(resp, self.url)
        self.assertFalse(Layanan.objects.exists())
        queue.assert_not_called()

    @mock.patch("layanan.views.queue_permohonan")
    def test_magang_and_gts_forms_also_save(self, queue):
        for name, jenis in (("layanan_magang", "Magang"), ("layanan_gts", "Goes To School")):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(reverse(name), _post_data(jenis_data=""))
            self.assertEqual(Layanan.objects.latest("pk").jenis_data, jenis)
        self.assertEqual(queue.call_count, 2)


class DashboardAccessTest(TestCase):
    def setUp(self):
        self.private = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.private, ignore_errors=True)
        rel = Path("layanan_surat/2026/10/1-abcd1234_surat.pdf")
        (Path(self.private) / rel).parent.mkdir(parents=True)
        (Path(self.private) / rel).write_bytes(b"%PDF")
        self.obj = Layanan.objects.create(nama="A", jenis_data="Magang", status="1", surat=str(rel))

    def test_dashboard_requires_login(self):
        for url in (reverse("layanan_dashboard_list"),
                    reverse("layanan_dashboard_detail", args=[self.obj.pk]),
                    reverse("layanan_dashboard_surat", args=[self.obj.pk])):
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 302, url)
            self.assertIn("/accounts/login/", resp["Location"])

    def test_staff_can_download_surat(self):
        self.client.force_login(User.objects.create_user("petugas", password="x"))
        with override_settings(PRIVATE_MEDIA_ROOT=self.private):
            resp = self.client.get(reverse("layanan_dashboard_surat", args=[self.obj.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('filename="surat.pdf"', resp["Content-Disposition"])
        self.assertEqual(b"".join(resp.streaming_content), b"%PDF")

    def test_surat_path_cannot_escape_private_root(self):
        self.obj.surat = "../../etc/passwd"
        self.obj.save()
        self.client.force_login(User.objects.create_user("petugas", password="x"))
        with override_settings(PRIVATE_MEDIA_ROOT=self.private):
            resp = self.client.get(reverse("layanan_dashboard_surat", args=[self.obj.pk]))
        self.assertEqual(resp.status_code, 404)


class NotifyTest(TestCase):
    def test_caption_escapes_and_lists_fields(self):
        obj = Layanan.objects.create(nama="Budi <b>", instansi="Uncen", email="b@x.id", handphone="0812",
                                     alamat="Abepura", jenis_data="Peta Kegempaan", status="1")
        text = caption(obj)
        self.assertIn(f"Permohonan PTSP baru #{obj.pk}", text)
        self.assertIn("Budi &lt;b&gt;", text)
        self.assertIn("Peta Kegempaan", text)
        self.assertLessEqual(len(text), 1024)

    @mock.patch("layanan.notify.send_telegram_document", return_value=True)
    def test_send_attaches_surat(self, send_doc):
        private = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, private, ignore_errors=True)
        rel = Path("layanan_surat/2026/10/9-abcd1234_Surat_Permohonan.pdf")
        (Path(private) / rel).parent.mkdir(parents=True)
        (Path(private) / rel).write_bytes(b"%PDF")
        obj = Layanan.objects.create(nama="A", jenis_data="Magang", status="1", surat=str(rel))
        with override_settings(PRIVATE_MEDIA_ROOT=private):
            self.assertTrue(send_permohonan(obj.pk))
        args, kwargs = send_doc.call_args
        self.assertEqual(args[0], b"%PDF")
        self.assertEqual(args[1], "Surat_Permohonan.pdf")
        self.assertEqual(kwargs["mime"], "application/pdf")

    @mock.patch("layanan.notify.send_telegram_message", return_value=True)
    def test_send_without_surat_falls_back_to_text(self, send_msg):
        obj = Layanan.objects.create(nama="A", jenis_data="Magang", status="1", surat="")
        self.assertTrue(send_permohonan(obj.pk))
        self.assertIn("surat tidak terlampir", send_msg.call_args[0][0])
