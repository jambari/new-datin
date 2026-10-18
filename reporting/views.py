import datetime
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from magnet.fmi_kindex import fmi_start_date
from magnet.kindex_import import import_kindex_workbook
from magnet.models import KIndexDaily

from .builders import kualitas_udara, magnet_petir, percepatan_tanah
from .common import Period
from .forms import REPORT_TYPES, KIndexUploadForm, ReportForm

logger = logging.getLogger(__name__)

UNIT_KERJA = "Stasiun Geofisika Jayapura"

BUILDERS = {
    "kualitas_udara": (kualitas_udara, "reporting/report_kualitas_udara.html"),
    "magnet_petir": (magnet_petir, "reporting/report_magnet_petir.html"),
    "percepatan_tanah": (percepatan_tanah, "reporting/report_percepatan_tanah.html"),
}


def officer(user):
    """Nama dan NIP pegawai yang login, dari profil jadwal.Pegawai bila terhubung."""
    pegawai = getattr(user, "pegawai", None)
    if pegawai is not None:
        return pegawai.nama, pegawai.nip
    return user.get_full_name() or user.get_username(), ""


def _initial(request):
    today = datetime.date.today()
    last_quarter_end = (today.month - 1) // 3 * 3 or 12
    year = today.year if last_quarter_end != 12 else today.year - 1
    return {
        "start_bulan": last_quarter_end - 2, "start_tahun": year,
        "end_bulan": last_quarter_end, "end_tahun": year,
    }


@login_required
def index(request):
    form = ReportForm(initial=_initial(request))
    nama, nip = officer(request.user)
    kindex_range = KIndexDaily.objects.order_by("tanggal").values_list("tanggal", flat=True)
    context = {
        "form": form,
        "officer_nama": nama,
        "officer_nip": nip,
        "unit_kerja": UNIT_KERJA,
        "upload_form": KIndexUploadForm(initial={"tahun": datetime.date.today().year}),
        "report_types": REPORT_TYPES,
        "kindex_first": kindex_range.first(),
        "kindex_last": kindex_range.last(),
        "kindex_count": kindex_range.count(),
        "kindex_fmi_start": fmi_start_date(),
    }
    return render(request, "reporting/index.html", context)


@login_required
def report(request):
    form = ReportForm(request.GET)
    if not form.is_valid():
        for err in form.non_field_errors():
            messages.error(request, err)
        for name, errs in form.errors.items():
            if name != "__all__":
                messages.error(request, f"{form.fields[name].label}: {'; '.join(errs)}")
        return redirect("reporting:index")
    data = dict(form.cleaned_data)
    nama, nip = officer(request.user)
    data["nama"] = nama
    data["nip"] = nip or data.get("nip", "")
    data["unit_kerja"] = UNIT_KERJA
    period = Period(data["start_tahun"], data["start_bulan"], data["end_tahun"], data["end_bulan"])
    module, template = BUILDERS[data["jenis"]]
    context = {
        "period": period,
        "identity": data,
        "title": module.TITLE,
        "report_label": dict(REPORT_TYPES)[data["jenis"]],
        "back_url": reverse("reporting:index"),
        "generated_at": datetime.datetime.now(),
        **module.build(period),
    }
    return render(request, template, context)


@login_required
@require_POST
def upload_kindex(request):
    form = KIndexUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        for errs in form.errors.values():
            for e in errs:
                messages.error(request, e)
        return redirect("reporting:index")
    upload = form.cleaned_data["berkas"]
    try:
        summary, warnings = import_kindex_workbook(upload, form.cleaned_data["tahun"], upload.name)
    except Exception as exc:  # berkas rusak / format lain
        logger.exception("Impor indeks K gagal")
        messages.error(request, f"Berkas tidak bisa dibaca sebagai Excel indeks K: {exc}")
        return redirect("reporting:index")
    for w in warnings:
        messages.warning(request, w)
    if summary:
        total = sum(c["data"] for c in summary.values())
        messages.success(request, f"Indeks K diimpor: {len(summary)} bulan, {total} hari berdata.")
    else:
        messages.warning(request, "Tidak ada sheet bulan (Januari–Desember) yang ditemukan di berkas.")
    return redirect("reporting:index")
