"""Lampiran Sampel Hujan: tabel hujan harian + keterangan sampling (format "SAMPEL HUJAN <tanggal>.docx").

Satu periode sampling = satu minggu (Selasa–Senin). Minggu ke- dihitung dari tanggal awal
di bulannya (29 September = minggu V September). Nama pengamat = pegawai berdinas PS
(Pagi Siang) di jadwal pada tanggal akhir query (hari pengambilan sampel, biasanya Senin).
"""
import io

from django.db.models import Q, Sum
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from jadwal.models import JadwalHarian

from .models import Hujan

NAMA_STASIUN = "Stasiun Geofisika Kelas I Jayapura"
POLA_SAMPLING = "PS"
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus",
         "September", "Oktober", "November", "Desember"]
MINGGU = [("I", "Satu"), ("II", "Dua"), ("III", "Tiga"), ("IV", "Empat"), ("V", "Lima")]
HEADER_BG = colors.HexColor("#3b82f6")
ROW_ALT = colors.HexColor("#f3f4f6")
LINE = colors.HexColor("#9ca3af")


def nama_singkat(nama):
    """'ALIF MUHAMMAD ANNABAL, S.Tr.Inst, M.Sc' -> 'Alif Muhammad Annabal' (tanpa gelar)."""
    return " ".join(w.capitalize() if w.isupper() else w for w in nama.split(",")[0].split())


def pengamat_sampling(tanggal):
    """Nama pegawai berdinas PS pada tanggal pengambilan sampel, urut sesuai jadwal."""
    rows = (JadwalHarian.objects
            .filter(tanggal=tanggal, pola__kode=POLA_SAMPLING)
            .filter(Q(keterangan_lain__isnull=True) | Q(keterangan_lain=""))
            .select_related("pegawai").order_by("pegawai__urutan", "pegawai__nama"))
    return [nama_singkat(j.pegawai.nama) for j in rows]


def sampling_info(start, end, kondisi="Baik"):
    """Keterangan di bawah tabel: periode/minggu ke-, bulan/tahun, jumlah mm, kondisi, pengamat."""
    week = min((start.day - 1) // 7, 4)
    roman, word = MINGGU[week]
    total = Hujan.objects.filter(tanggal__range=[start, end]).aggregate(s=Sum("obs"))["s"] or 0
    return {
        "nama_stasiun": NAMA_STASIUN,
        "minggu": f"{roman} ({word}) / {roman} ({word})",
        "bulan_tahun": f"{BULAN[start.month - 1]} / {start.year}",
        "total": total,
        "kondisi": kondisi or "Baik",
        "pengamat": pengamat_sampling(end),
    }


def lampiran_pdf(records, info):
    """PDF A4 potret: judul, tabel hujan harian, lalu keterangan sampling."""
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm,
                            title="Lampiran Sampel Hujan", author=NAMA_STASIUN)
    title = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=12, leading=15, alignment=TA_CENTER)
    cell = ParagraphStyle("c", fontName="Helvetica-Bold", fontSize=7.5, leading=9.5, alignment=TA_CENTER)
    info_style = ParagraphStyle("i", fontName="Helvetica", fontSize=11, leading=14)

    data = [["NO", "TANGGAL", "JUMLAH (MM)", "KATEGORI", "PENGAMAT"]]
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for i, h in enumerate(records, start=1):
        kategori = (h.kategori or "").lower()
        data.append([str(i), h.tanggal.strftime("%d-%m-%Y"), f"{h.obs:.1f}", kategori,
                     Paragraph(h.petugas or "-", cell)])
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), ROW_ALT))
        if kategori == "nihil":
            style += [("FONTNAME", (3, i), (3, i), "Helvetica-Oblique"), ("TEXTCOLOR", (3, i), (3, i), colors.grey)]
        elif kategori == "sangat lebat":
            style.append(("TEXTCOLOR", (3, i), (3, i), colors.red))
    n = len(data)
    data.append(["Total:", "", f"{info['total']:.1f} mm", "", ""])
    style += [("SPAN", (0, n), (1, n)), ("BACKGROUND", (0, n), (-1, n), colors.HexColor("#f9fafb"))]

    table = Table(data, colWidths=[1.6 * cm, 3.5 * cm, 3.5 * cm, 4.2 * cm, 4.2 * cm], repeatRows=1)
    table.setStyle(TableStyle(style))

    rows = [["Nama Stasiun", f": {info['nama_stasiun']}"],
            ["Periode Sampling / Minggu ke", f": {info['minggu']}"],
            ["Bulan / Tahun", f": {info['bulan_tahun']}"],
            ["Jumlah mm dari penakar hujan obs", Paragraph(f"<b>: {info['total']:.1f} <i>mm</i></b>", info_style)],
            ["Kondisi Sampling", f": {info['kondisi']}"],
            ["Nama Pengamat", ":"]]
    rows += [["", f"-    {nama}"] for nama in info["pengamat"] or ["-"]]
    keterangan = Table(rows, colWidths=[7.5 * cm, 9.5 * cm], hAlign="LEFT")
    keterangan.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    doc.build([Paragraph(NAMA_STASIUN, title), Paragraph("Laporan Hujan Harian", title), Spacer(1, 0.7 * cm),
               table, Spacer(1, 0.6 * cm), keterangan])
    return out.getvalue()
