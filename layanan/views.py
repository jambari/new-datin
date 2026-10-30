import re
import uuid
from pathlib import Path

from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, Http404
from django.utils import timezone
from .models import Layanan
from .notify import queue_permohonan

JENIS_DATA_MAP = {
    1: ("Peta Kegempaan", "kegempaan.jpg"),
    2: ("Peta Tingkat Kerawanan Petir", "kerawananpetir.jpg"),
    3: ("Waktu Terbit dan Terbenam Matahari atau Bulan", "terbit.jpg"),
    4: ("Peta Kejadian Petir", "petirharian.jpg"),
    5: ("Teropong Rukyat (low grade)", "page06.jpg"),
    6: ("Digital Portable Short Period Seismograph", "page07.jpg"),
    7: ("Deklinasi dan Inklinasi Magnetometer", "page08.jpg"),
}


# ── Public pages ──────────────────────────────────────────────

def landing(request):
    return render(request, 'layanan/landing.html')

def tentang(request):
    return render(request, 'layanan/tentang.html')

def tarif(request):
    return render(request, 'layanan/tarif.html')

def alur(request):
    return render(request, 'layanan/alur.html')

def data(request):
    return render(request, 'layanan/data.html')

def jasa(request):
    return render(request, 'layanan/jasa.html')

def magang(request):
    return _form_page(request, 'layanan/magang.html', {}, "Magang")

def gts(request):
    return _form_page(request, 'layanan/gts.html', {}, "Goes To School")

def formulir(request, id):
    jenis_data, jpg = JENIS_DATA_MAP.get(id, ("Deklinasi dan Inklinasi Magnetometer", "page08.jpg"))
    return _form_page(request, 'layanan/formulir.html', {'jenis_data': jenis_data, 'jpg': jpg, 'id': id}, jenis_data)


# ── Formulir permohonan (layanan/_form.html) ──────────────────

FORM_FIELDS = ("nama", "instansi", "alamat", "email", "handphone", "jenis_data")
SURAT_EXT = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"}
SURAT_MAX_BYTES = 10 * 1024 * 1024


def _form_page(request, template, context, jenis_default):
    """GET: tampilkan formulir. POST: simpan permohonan + surat, kabarkan ke Telegram, redirect."""
    form_data, errors = {}, []
    if request.method == "POST":
        if request.POST.get("website"):             # honeypot: hanya bot yang mengisinya
            messages.success(request, "Permohonan Anda sudah kami terima.")
            return redirect(request.path)
        form_data = {f: (request.POST.get(f) or "").strip()[:255] for f in FORM_FIELDS}
        form_data["jenis_data"] = form_data["jenis_data"] or jenis_default
        errors = _validate(form_data, request.FILES.get("surat"))
        if not errors:
            with transaction.atomic():
                layanan = Layanan.objects.create(**form_data, status="1")
                layanan.surat = _save_surat(request.FILES["surat"], layanan.pk)
                layanan.save(update_fields=["surat"])
                transaction.on_commit(lambda: queue_permohonan(layanan.pk))
            messages.success(request, f"Permohonan Anda (nomor #{layanan.pk}) sudah kami terima. "
                                      "Kami akan menghubungi Anda melalui email atau nomor HP.")
            return redirect(request.path)
    return render(request, template, {**context, "form_data": form_data, "form_errors": errors})


def _validate(data, surat):
    labels = {"nama": "Nama", "instansi": "Instansi", "alamat": "Alamat", "email": "Email",
              "handphone": "No. Handphone", "jenis_data": "Jenis permohonan"}
    errors = [f"{labels[f]} wajib diisi." for f in FORM_FIELDS if not data[f]]
    if data["email"]:
        try:
            validate_email(data["email"])
        except ValidationError:
            errors.append("Alamat email tidak valid.")
    if data["handphone"] and not re.fullmatch(r"[+\d][\d\s-]{6,19}", data["handphone"]):
        errors.append("Nomor handphone tidak valid.")
    if not surat:
        errors.append("Surat permohonan wajib diunggah.")
    elif Path(surat.name).suffix.lower() not in SURAT_EXT:
        errors.append("Surat harus berupa PDF, JPG, PNG, atau DOC/DOCX.")
    elif surat.size > SURAT_MAX_BYTES:
        errors.append("Ukuran surat maksimal 10 MB.")
    return errors


def _save_surat(upload, pk):
    """Simpan di PRIVATE_MEDIA_ROOT (tidak disajikan nginx); kembalikan path relatif."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(upload.name).name).strip("._")[:80] or "surat"
    rel = Path("layanan_surat") / timezone.now().strftime("%Y/%m") / f"{pk}-{uuid.uuid4().hex[:8]}_{safe}"
    dest = Path(settings.PRIVATE_MEDIA_ROOT) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as fh:
        for chunk in upload.chunks():
            fh.write(chunk)
    return str(rel)

def daftar(request):
    permohonans = Layanan.objects.all()
    paginator = Paginator(permohonans, 10)
    page = request.GET.get('page', 1)
    return render(request, 'layanan/daftar.html', {'permohonans': paginator.get_page(page)})


# ── Dashboard CRUD ────────────────────────────────────────────

@login_required
def dashboard_list(request):
    qs = Layanan.objects.all()
    paginator = Paginator(qs, 20)
    page = request.GET.get('page', 1)
    return render(request, 'layanan/dashboard_list.html', {
        'layanan_list': paginator.get_page(page),
    })


@login_required
def dashboard_detail(request, pk):
    layanan = get_object_or_404(Layanan, pk=pk)
    if request.method == 'POST':
        layanan.status = request.POST.get('status', layanan.status)
        layanan.save(update_fields=['status'])
        messages.success(request, 'Status berhasil diperbarui.')
        return redirect('layanan_dashboard_detail', pk=pk)
    return render(request, 'layanan/dashboard_detail.html', {'layanan': layanan})


@login_required
def dashboard_surat(request, pk):
    layanan = get_object_or_404(Layanan, pk=pk)
    root = Path(settings.PRIVATE_MEDIA_ROOT).resolve()
    path = (root / (layanan.surat or "")).resolve()
    if not layanan.surat or root not in path.parents or not path.is_file():
        raise Http404("Surat tidak ditemukan.")
    return FileResponse(open(path, "rb"), as_attachment=True, filename=path.name.split("_", 1)[-1])
