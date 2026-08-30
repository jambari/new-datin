import io
from datetime import datetime
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload

from .forms import (
    LaporanPMUploadForm,
    ManajemenSukuCadangForm,
    PeminjamanForm,
    PeralatanForm,
    PeralatanSukuCadangForm,
    UnduhDataForm,
)
from .models import ManajemenSukuCadang, Peminjaman, Peralatan, PeralatanSukuCadang


PER_PAGE_OPTIONS = (10, 25, 50, 100)
MANAJEMEN_EXPORT_HEADERS = [
    "Tanggal Masuk",
    "Jenis",
    "Merk",
    "Serial Number",
    "Jumlah",
    "Status",
    "Keterangan",
]
PEMINJAMAN_EXPORT_HEADERS = [
    "Tanggal Peminjaman",
    "No. ST",
    "Nama Alat",
    "Status",
    "Keterangan",
]


def get_per_page_value(request, default=10):
    try:
        value = int(request.GET.get("per_page", default))
    except (TypeError, ValueError):
        return default
    return value if value in PER_PAGE_OPTIONS else default


def build_preserved_params(request, exclude=None):
    exclude = exclude or {"page", "export"}
    params = {}
    for key, value in request.GET.items():
        if key not in exclude and value:
            params[key] = value
    return params


def build_filter_query(request, exclude=None):
    return "&".join(
        f"{key}={value}"
        for key, value in build_preserved_params(request, exclude).items()
    )


def paginate_queryset(request, queryset, per_page=10):
    paginator = Paginator(queryset, per_page)
    page = request.GET.get("page")
    try:
        return paginator.page(page)
    except PageNotAnInteger:
        return paginator.page(1)
    except EmptyPage:
        return paginator.page(paginator.num_pages)


def get_manajemen_suku_cadang_queryset(request):
    status_filter = request.GET.get("status")
    tanggal_filter = request.GET.get("tanggal_masuk")
    queryset = ManajemenSukuCadang.objects.select_related("jenis").all()
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    if tanggal_filter:
        queryset = queryset.filter(tanggal_masuk=tanggal_filter)
    return queryset, status_filter, tanggal_filter


def iter_manajemen_export_rows(queryset):
    for item in queryset:
        yield [
            item.tanggal_masuk.strftime("%d-%m-%Y"),
            item.jenis.jenis_alat,
            item.merk,
            item.serial_number,
            item.jumlah,
            item.get_status_display(),
            item.keterangan or "-",
        ]


def iter_peminjaman_export_rows(queryset):
    for item in queryset:
        yield [
            item.tanggal_peminjaman.strftime("%d-%m-%Y"),
            item.surat_tugas,
            item.get_peralatan_names_display(),
            item.get_status_display(),
            item.keterangan or "-",
        ]


def export_table_excel(sheet_title, headers, row_iterator, filename_prefix):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_title
    sheet.append(headers)
    for row in row_iterator:
        sheet.append(row)

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    filename = f"{filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def export_table_pdf(doc_title, headers, row_iterator, filename_prefix):
    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=landscape(A4), leftMargin=24, rightMargin=24)
    styles = getSampleStyleSheet()
    elements = [
        Paragraph(doc_title, styles["Title"]),
        Spacer(1, 12),
    ]

    table_data = [headers]
    table_data.extend(row_iterator)
    table = Table(table_data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    elements.append(table)
    document.build(elements)

    filename = f"{filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    response = HttpResponse(output.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def export_manajemen_suku_cadang(queryset, export_format):
    if export_format == "excel":
        return export_table_excel(
            "Manajemen Suku Cadang",
            MANAJEMEN_EXPORT_HEADERS,
            iter_manajemen_export_rows(queryset),
            "manajemen_suku_cadang",
        )
    return export_table_pdf(
        "Data Manajemen Suku Cadang",
        MANAJEMEN_EXPORT_HEADERS,
        iter_manajemen_export_rows(queryset),
        "manajemen_suku_cadang",
    )


def export_peminjaman(queryset, export_format):
    if export_format == "excel":
        return export_table_excel(
            "Peminjaman",
            PEMINJAMAN_EXPORT_HEADERS,
            iter_peminjaman_export_rows(queryset),
            "peminjaman",
        )
    return export_table_pdf(
        "Data Peminjaman Peralatan Teknis",
        PEMINJAMAN_EXPORT_HEADERS,
        iter_peminjaman_export_rows(queryset),
        "peminjaman",
    )


@login_required
def index(request):
    context = {
        "total_peralatan": Peralatan.objects.count(),
    }
    return render(request, "monitoring_pm/index.html", context)


@login_required
def peralatan_list(request):
    status_filter = request.GET.get("status")
    queryset = Peralatan.objects.all().order_by("nama_alat")
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    context = {
        "peralatan_list": paginate_queryset(request, queryset),
        "status_choices": Peralatan.STATUS_CHOICES,
        "selected_status": status_filter,
    }
    return render(request, "monitoring_pm/peralatan_list.html", context)


@login_required
def peralatan_create(request):
    if request.method == "POST":
        form = PeralatanForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("monitoring_pm:peralatan_list")
    else:
        form = PeralatanForm()

    return render(
        request,
        "monitoring_pm/form_generic.html",
        {
            "form": form,
            "title": "Tambah Peralatan",
            "back_url": "monitoring_pm:peralatan_list",
        },
    )


@login_required
def peralatan_update(request, pk):
    peralatan = get_object_or_404(Peralatan, pk=pk)
    if request.method == "POST":
        form = PeralatanForm(request.POST, instance=peralatan)
        if form.is_valid():
            form.save()
            return redirect("monitoring_pm:peralatan_list")
    else:
        form = PeralatanForm(instance=peralatan)

    return render(
        request,
        "monitoring_pm/form_generic.html",
        {
            "form": form,
            "title": f"Edit Peralatan: {peralatan.nama_alat}",
            "back_url": "monitoring_pm:peralatan_list",
        },
    )


@login_required
def peralatan_delete(request, pk):
    peralatan = get_object_or_404(Peralatan, pk=pk)
    if request.method == "POST":
        peralatan.delete()
        return redirect("monitoring_pm:peralatan_list")

    return render(
        request,
        "monitoring_pm/confirm_delete.html",
        {
            "object": peralatan,
            "type_name": "Peralatan",
            "back_url": "monitoring_pm:peralatan_list",
        },
    )


@login_required
def peminjaman_list(request):
    status_filter = request.GET.get("status")
    tanggal_filter = request.GET.get("tanggal_peminjaman")
    queryset = Peminjaman.objects.all().order_by("-tanggal_peminjaman", "-created_at", "-id")
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    if tanggal_filter:
        queryset = queryset.filter(tanggal_peminjaman=tanggal_filter)

    per_page = get_per_page_value(request)
    peminjaman_list = paginate_queryset(request, queryset, per_page=per_page)
    page_range = peminjaman_list.paginator.get_elided_page_range(
        peminjaman_list.number,
        on_each_side=2,
        on_ends=2,
    )

    context = {
        "peminjaman_list": peminjaman_list,
        "page_range": page_range,
        "page_obj": peminjaman_list,
        "per_page": per_page,
        "per_page_options": PER_PAGE_OPTIONS,
        "preserved_params": build_preserved_params(request, exclude={"page"}),
        "filter_query": build_filter_query(request, exclude={"page"}),
        "status_choices": Peminjaman.STATUS_CHOICES,
        "selected_status": status_filter,
        "selected_tanggal_peminjaman": tanggal_filter,
        "total_label": "Peminjaman",
    }
    return render(request, "monitoring_pm/peminjaman_list.html", context)


@login_required
def peminjaman_create(request):
    if request.method == "POST":
        form = PeminjamanForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("monitoring_pm:peminjaman_list")
    else:
        form = PeminjamanForm()

    return render(
        request,
        "monitoring_pm/form_generic.html",
        {
            "form": form,
            "title": "Tambah Peminjaman",
            "back_url": "monitoring_pm:peminjaman_list",
        },
    )


@login_required
def peminjaman_update(request, pk):
    peminjaman = get_object_or_404(Peminjaman, pk=pk)
    if request.method == "POST":
        form = PeminjamanForm(request.POST, instance=peminjaman)
        if form.is_valid():
            form.save()
            return redirect("monitoring_pm:peminjaman_list")
    else:
        form = PeminjamanForm(instance=peminjaman)

    return render(
        request,
        "monitoring_pm/form_generic.html",
        {
            "form": form,
            "title": f"Edit Peminjaman: {peminjaman.surat_tugas}",
            "back_url": "monitoring_pm:peminjaman_list",
        },
    )


@login_required
def peminjaman_delete(request, pk):
    peminjaman = get_object_or_404(Peminjaman, pk=pk)
    if request.method == "POST":
        peminjaman.delete()
        return redirect("monitoring_pm:peminjaman_list")

    return render(
        request,
        "monitoring_pm/confirm_delete.html",
        {
            "object": peminjaman,
            "type_name": "Peminjaman",
            "back_url": "monitoring_pm:peminjaman_list",
        },
    )


@login_required
def laporan_list(request):
    if request.method == "POST":
        form = LaporanPMUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                upload_laporan_pm_to_drive(
                    tahun=form.cleaned_data["tahun"],
                    kota=form.cleaned_data["kota_tujuan"],
                    uploaded_file=request.FILES["dokumen"],
                )
                messages.success(request, "Dokumen berhasil diupload ke Google Drive Laporan PM.")
                return redirect("monitoring_pm:laporan_list")
            except Exception as exc:
                messages.error(request, f"Gagal upload dokumen: {format_drive_error(exc)}")
    else:
        form = LaporanPMUploadForm()

    return render(request, "monitoring_pm/laporan_list.html", {"form": form})


@login_required
def suku_cadang_peralatan_list(request):
    queryset = PeralatanSukuCadang.objects.all().order_by("jenis_alat")
    context = {
        "peralatan_list": paginate_queryset(request, queryset),
    }
    return render(request, "monitoring_pm/suku_cadang_peralatan_list.html", context)


@login_required
def suku_cadang_peralatan_create(request):
    if request.method == "POST":
        form = PeralatanSukuCadangForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("monitoring_pm:suku_cadang_peralatan_list")
    else:
        form = PeralatanSukuCadangForm()

    return render(
        request,
        "monitoring_pm/form_generic.html",
        {
            "form": form,
            "title": "Tambah Peralatan Suku Cadang",
            "back_url": "monitoring_pm:suku_cadang_peralatan_list",
        },
    )


@login_required
def suku_cadang_peralatan_update(request, pk):
    peralatan = get_object_or_404(PeralatanSukuCadang, pk=pk)
    if request.method == "POST":
        form = PeralatanSukuCadangForm(request.POST, instance=peralatan)
        if form.is_valid():
            form.save()
            return redirect("monitoring_pm:suku_cadang_peralatan_list")
    else:
        form = PeralatanSukuCadangForm(instance=peralatan)

    return render(
        request,
        "monitoring_pm/form_generic.html",
        {
            "form": form,
            "title": f"Edit Peralatan: {peralatan.jenis_alat}",
            "back_url": "monitoring_pm:suku_cadang_peralatan_list",
        },
    )


@login_required
def suku_cadang_peralatan_delete(request, pk):
    peralatan = get_object_or_404(PeralatanSukuCadang, pk=pk)
    if request.method == "POST":
        peralatan.delete()
        return redirect("monitoring_pm:suku_cadang_peralatan_list")

    return render(
        request,
        "monitoring_pm/confirm_delete.html",
        {
            "object": peralatan,
            "type_name": "Peralatan Suku Cadang",
            "back_url": "monitoring_pm:suku_cadang_peralatan_list",
        },
    )


@login_required
def suku_cadang_manajemen_list(request):
    queryset, status_filter, tanggal_filter = get_manajemen_suku_cadang_queryset(request)
    per_page = get_per_page_value(request)
    manajemen_list = paginate_queryset(request, queryset, per_page=per_page)
    page_range = manajemen_list.paginator.get_elided_page_range(
        manajemen_list.number,
        on_each_side=2,
        on_ends=2,
    )

    context = {
        "manajemen_list": manajemen_list,
        "page_range": page_range,
        "page_obj": manajemen_list,
        "per_page": per_page,
        "per_page_options": PER_PAGE_OPTIONS,
        "preserved_params": build_preserved_params(request, exclude={"page"}),
        "filter_query": build_filter_query(request, exclude={"page"}),
        "status_choices": ManajemenSukuCadang.STATUS_CHOICES,
        "selected_status": status_filter,
        "selected_tanggal_masuk": tanggal_filter,
        "total_label": "Manajemen Suku Cadang",
    }
    return render(request, "monitoring_pm/suku_cadang_manajemen_list.html", context)


@login_required
def suku_cadang_unduh_data(request):
    if request.method == "POST":
        form = UnduhDataForm(request.POST)
        if form.is_valid():
            tanggal_mulai = form.cleaned_data["tanggal_mulai"]
            tanggal_selesai = form.cleaned_data["tanggal_selesai"]
            export_format = form.cleaned_data["format"]
            queryset = ManajemenSukuCadang.objects.select_related("jenis").filter(
                tanggal_masuk__gte=tanggal_mulai,
                tanggal_masuk__lte=tanggal_selesai,
            )
            return export_manajemen_suku_cadang(queryset, export_format)
    else:
        form = UnduhDataForm()

    return render(
        request,
        "monitoring_pm/unduh_data.html",
        {
            "form": form,
            "title": "Unduh Data Suku Cadang",
            "description": "Unduh data manajemen suku cadang berdasarkan rentang tanggal masuk.",
        },
    )


@login_required
def peminjaman_unduh_data(request):
    if request.method == "POST":
        form = UnduhDataForm(request.POST)
        if form.is_valid():
            tanggal_mulai = form.cleaned_data["tanggal_mulai"]
            tanggal_selesai = form.cleaned_data["tanggal_selesai"]
            export_format = form.cleaned_data["format"]
            queryset = Peminjaman.objects.filter(
                tanggal_peminjaman__gte=tanggal_mulai,
                tanggal_peminjaman__lte=tanggal_selesai,
            ).order_by("-tanggal_peminjaman", "-created_at")
            return export_peminjaman(queryset, export_format)
    else:
        form = UnduhDataForm()

    return render(
        request,
        "monitoring_pm/unduh_data.html",
        {
            "form": form,
            "title": "Unduh Data Peralatan Teknis",
            "description": "Unduh data peminjaman peralatan teknis berdasarkan rentang tanggal peminjaman.",
        },
    )


@login_required
def suku_cadang_manajemen_create(request):
    if request.method == "POST":
        form = ManajemenSukuCadangForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("monitoring_pm:suku_cadang_manajemen_list")
    else:
        form = ManajemenSukuCadangForm()

    return render(
        request,
        "monitoring_pm/form_generic.html",
        {
            "form": form,
            "title": "Tambah Manajemen",
            "back_url": "monitoring_pm:suku_cadang_manajemen_list",
        },
    )


@login_required
def suku_cadang_manajemen_update(request, pk):
    manajemen = get_object_or_404(ManajemenSukuCadang, pk=pk)
    if request.method == "POST":
        form = ManajemenSukuCadangForm(request.POST, instance=manajemen)
        if form.is_valid():
            form.save()
            return redirect("monitoring_pm:suku_cadang_manajemen_list")
    else:
        form = ManajemenSukuCadangForm(instance=manajemen)

    return render(
        request,
        "monitoring_pm/form_generic.html",
        {
            "form": form,
            "title": f"Edit Manajemen: {manajemen}",
            "back_url": "monitoring_pm:suku_cadang_manajemen_list",
        },
    )


@login_required
def suku_cadang_manajemen_delete(request, pk):
    manajemen = get_object_or_404(ManajemenSukuCadang, pk=pk)
    if request.method == "POST":
        manajemen.delete()
        return redirect("monitoring_pm:suku_cadang_manajemen_list")

    return render(
        request,
        "monitoring_pm/confirm_delete.html",
        {
            "object": manajemen,
            "type_name": "Manajemen Suku Cadang",
            "back_url": "monitoring_pm:suku_cadang_manajemen_list",
        },
    )


def build_drive_service():
    credentials_file = settings.GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE
    if not credentials_file:
        default_path = Path(settings.BASE_DIR) / "service-account.json"
        if default_path.exists():
            credentials_file = str(default_path)

    if not credentials_file:
        raise ValueError(
            "GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE belum diatur. "
            "Set env var GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE atau simpan file "
            "service-account.json di root project."
        )

    credentials = service_account.Credentials.from_service_account_file(
        credentials_file,
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def get_or_create_drive_folder(service, folder_name, parent_folder_id):
    safe_name = folder_name.replace("'", "\\'")
    query = (
        "mimeType='application/vnd.google-apps.folder' "
        f"and name='{safe_name}' and '{parent_folder_id}' in parents and trashed=false"
    )
    response = (
        service.files()
        .list(
            q=query,
            fields="files(id, name)",
            pageSize=1,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
        )
        .execute()
    )
    files = response.get("files", [])
    if files:
        return files[0]["id"]

    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_folder_id],
    }
    created = (
        service.files()
        .create(
            body=metadata,
            fields="id",
            supportsAllDrives=True,
        )
        .execute()
    )
    return created["id"]


def upload_laporan_pm_to_drive(tahun, kota, uploaded_file):
    root_folder_id = settings.LAPORAN_PM_DRIVE_FOLDER_ID
    service = build_drive_service()
    if not root_folder_id:
        parent_laporan_operasional_id = settings.LAPORAN_OPERASIONAL_DRIVE_FOLDER_ID
        if not parent_laporan_operasional_id:
            raise ValueError("LAPORAN_PM_DRIVE_FOLDER_ID belum diatur.")
        root_folder_id = get_or_create_drive_folder(service, "Laporan PM", parent_laporan_operasional_id)

    tahun_folder_id = get_or_create_drive_folder(service, str(tahun), root_folder_id)
    kota_folder_id = get_or_create_drive_folder(service, kota, tahun_folder_id)

    file_content = uploaded_file.read()
    media = MediaIoBaseUpload(
        io.BytesIO(file_content),
        mimetype=uploaded_file.content_type or "application/octet-stream",
        resumable=False,
    )
    metadata = {
        "name": uploaded_file.name,
        "parents": [kota_folder_id],
    }
    service.files().create(
        body=metadata,
        media_body=media,
        fields="id,name",
        supportsAllDrives=True,
    ).execute()


def format_drive_error(exc):
    if isinstance(exc, HttpError):
        error_text = str(exc)
        if "storageQuotaExceeded" in error_text:
            return (
                "Service account tidak bisa upload ke My Drive karena tidak punya kuota. "
                "Pindahkan folder tujuan ke Shared Drive, lalu beri akses minimal Content Manager "
                "ke service account. Setelah itu gunakan kembali folder ID Shared Drive tersebut."
            )
    return str(exc)
