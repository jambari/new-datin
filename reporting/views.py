import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from magnet.fmi_kindex import fmi_start_date
from magnet.models import KIndexDaily

from .builders import gempabumi, gempabumi_cepat, hujan, kualitas_udara, magnet_petir, percepatan_tanah
from .common import Period
from .forms import REPORT_TYPES, ReportForm

UNIT_KERJA = "Stasiun Geofisika Jayapura"

BUILDERS = {
    "kualitas_udara": (kualitas_udara, "reporting/report_kualitas_udara.html"),
    "magnet_petir": (magnet_petir, "reporting/report_magnet_petir.html"),
    "percepatan_tanah": (percepatan_tanah, "reporting/report_percepatan_tanah.html"),
    "hujan": (hujan, "reporting/report_hujan.html"),
    "gempabumi": (gempabumi, "reporting/report_gempabumi.html"),
    "gempabumi_cepat": (gempabumi_cepat, "reporting/report_gempabumi_cepat.html"),
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
        **(module.build(period, officer=getattr(request.user, "pegawai", None))
           if getattr(module, "PER_OFFICER", False) else module.build(period)),
    }
    return render(request, template, context)
