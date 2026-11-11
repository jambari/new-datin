"""Ekspor PDF halaman peta isoseismal: peta lalu penjelasan yang sama dengan halaman web.

reportlab (sudah dipakai qc_review). Huruf DejaVu Sans dari matplotlib (sudah dipakai untuk
menggambar peta) karena Helvetica bawaan tidak punya '≥' dan sejenisnya.
"""
import io
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONT, FONT_BOLD = 'DejaVuSans', 'DejaVuSans-Bold'
TEXT_W = A4[0] - 3.6 * cm
GREY = colors.HexColor('#64748b')
ABOUT = ('Peta isoseismal menggambarkan daerah-daerah dengan intensitas guncangan yang sama dalam skala MMI '
         '(Modified Mercalli Intensity). Warna peta adalah perkiraan intensitas dari ShakeMap Stasiun Geofisika '
         'Jayapura yang dikoreksi dengan rekaman akselerograf BMKG; titik bulat adalah laporan dirasakan dari '
         'masyarakat, BMKG, dan katalog stasiun. Peta dibuat otomatis dan dapat diperbarui bila ada laporan baru.')


def _fonts():
    if FONT in pdfmetrics.getRegisteredFontNames():
        return
    import matplotlib
    ttf = Path(matplotlib.get_data_path()) / 'fonts' / 'ttf'
    pdfmetrics.registerFont(TTFont(FONT, str(ttf / 'DejaVuSans.ttf')))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(ttf / 'DejaVuSans-Bold.ttf')))
    pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD, italic=FONT, boldItalic=FONT_BOLD)


def _styles():
    body = ParagraphStyle('body', fontName=FONT, fontSize=9, leading=12.5, spaceAfter=5)
    return {
        'title': ParagraphStyle('title', parent=body, fontName=FONT_BOLD, fontSize=14, leading=18, spaceAfter=2),
        'meta': ParagraphStyle('meta', parent=body, fontSize=8.5, textColor=GREY, spaceAfter=8),
        'h': ParagraphStyle('h', parent=body, fontName=FONT_BOLD, fontSize=10.5, leading=14, spaceBefore=8, spaceAfter=4),
        'body': body,
        'note': ParagraphStyle('note', parent=body, fontSize=7.5, leading=10, textColor=GREY),
        'cell': ParagraphStyle('cell', parent=body, fontSize=8, leading=10, spaceAfter=0),
        'badge': ParagraphStyle('badge', parent=body, fontName=FONT_BOLD, fontSize=8, leading=10, spaceAfter=0,
                                alignment=TA_CENTER),
    }


def _table(header, rows, widths, st, badge_col=None, badge_colors=()):
    data = [[Paragraph(f'<b>{escape(h)}</b>', st['cell']) for h in header]]
    for row in rows:
        data.append([Paragraph(escape(str(c)), st['badge'] if i == badge_col else st['cell'])
                     for i, c in enumerate(row)])
    scale = TEXT_W / sum(widths)                       # lebar relatif → selebar teks
    t = Table(data, colWidths=[w * scale for w in widths], repeatRows=1)
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
        ('LINEBELOW', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]
    if badge_col is not None:
        style += [('BACKGROUND', (badge_col, r + 1), (badge_col, r + 1), colors.HexColor(c))
                  for r, c in enumerate(badge_colors) if c]
    t.setStyle(TableStyle(style))
    return t


def _map_image(obj):
    with obj.image.open('rb') as fh:
        data = io.BytesIO(fh.read())
    w, h = ImageReader(data).getSize()
    data.seek(0)
    width = TEXT_W
    height = width * h / w
    max_h = A4[1] * 0.55
    if height > max_h:
        width, height = width * max_h / height, max_h
    return Image(data, width=width, height=height)


def build_pdf(obj, ctx, url):
    """PDF (bytes) untuk satu peta. ctx = konteks halaman detail (felt, stations, wilayah, tektonik, …)."""
    _fonts()
    st = _styles()
    story = [
        Paragraph(escape(obj.title), st['title']),
        Paragraph(f'{escape(obj.tanggal_panjang)} · Stasiun Geofisika Kelas I Jayapura – BMKG', st['meta']),
    ]
    if obj.image:
        story += [_map_image(obj), Spacer(1, 8)]

    intro = (f'Gempabumi terjadi pada {obj.tanggal_panjang} pukul {obj.jam} WIT dengan magnitudo '
             f'<b>M {obj.magnitude:.1f}</b> pada kedalaman {obj.depth:.0f} km, berpusat di {obj.koordinat}'
             + (f' ({escape(obj.lokasi)})' if obj.lokasi else '') + '.')
    if ctx.get('mmi_max'):
        intro += f" Intensitas tertinggi yang teramati <b>{ctx['mmi_max']['label']} MMI</b> ({escape(ctx['mmi_max']['desc'].lower())})."
    story.append(Paragraph(intro, st['body']))
    story.append(_table(['Waktu', 'Magnitudo', 'Kedalaman', 'Lokasi'],
                        [[f'{obj.waktu} WIT', f'M {obj.magnitude:.1f}', f'{obj.depth:.0f} km', obj.koordinat]],
                        [4.6, 3.0, 3.0, 7.2], st))

    felt = ctx.get('felt') or []
    if felt:
        block = [Paragraph('Laporan dirasakan', st['h']),
                 _table(['Tempat', 'MMI', 'Keterangan'],
                        [[f['place'], f['mmi_text'], f['band']['desc'] if f.get('band') else ''] for f in felt],
                        [5.0, 2.0, 10.8], st, badge_col=1,
                        badge_colors=[f['band']['color'] if f.get('band') else None for f in felt])]
        if obj.felt_text:
            block.append(Paragraph('Teks laporan: ' + escape(obj.felt_text).replace('\n', '<br/>'), st['note']))
        story.append(KeepTogether(block))
    else:
        story.append(Paragraph('Gempa ini tercatat dirasakan, tetapi laporan intensitas (skala MMI) per wilayah belum '
                               'tersedia. Peta menampilkan perkiraan intensitas ShakeMap dan rekaman akselerograf.',
                               st['note']))

    stations = ctx.get('stations') or []
    if stations:
        def num(v, fmt):
            return '–' if v is None else format(v, fmt) if isinstance(v, (int, float)) else str(v)
        story.append(KeepTogether([
            Paragraph('Rekaman akselerograf', st['h']),
            _table(['Stasiun', 'Jarak (km)', 'PGA (%g)', 'PGV (cm/s)', 'MMI instrumental'],
                   [[s['code'], num(s.get('dist_km'), '.0f'), num(s.get('pga'), ''), num(s.get('pgv'), ''),
                     f"{s['roman']} ({s['mmi']})" if s.get('band') else '–'] for s in stations],
                   [3.2, 2.8, 2.8, 2.8, 6.2], st, badge_col=4,
                   badge_colors=[s['band']['color'] if s.get('band') else None for s in stations])]))

    wilayah = ctx.get('wilayah') or []
    if wilayah:
        story.append(KeepTogether([
            Paragraph('Perkiraan intensitas per kabupaten/kota', st['h']),
            _table(['Wilayah', 'MMI maks. (perkiraan)'],
                   [[w['name'], f"{w['band']['label']} ({w['mmi']})"] for w in wilayah],
                   [10.0, 7.8], st, badge_col=1, badge_colors=[w['band']['color'] for w in wilayah])]))

    if ctx.get('tektonik'):
        paras = [Paragraph(escape(p), st['body']) for p in ctx['tektonik']]
        story += [KeepTogether([Paragraph('Tatanan tektonik', st['h']), paras[0]]), *paras[1:],
                  Paragraph(escape(ctx['tektonik_sumber']), st['note'])]

    if ctx.get('sumber'):
        story.append(KeepTogether([
            Paragraph('Sumber gempa terdekat', st['h']),
            Paragraph('<br/>'.join(escape(line) for line in ctx['sumber']), st['body']),
            Paragraph('Menurut model sumber gempa PuSGeN 2024; petunjuk saja, bukan penentuan sumber gempa.',
                      st['note'])]))

    story.append(KeepTogether([Paragraph('Tentang peta isoseismal', st['h']), Paragraph(ABOUT, st['body'])]))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(FONT, 7)
        canvas.setFillColor(GREY)
        canvas.drawString(1.8 * cm, 1.0 * cm, url)
        canvas.drawRightString(A4[0] - 1.8 * cm, 1.0 * cm, f'Halaman {doc.page}')
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.6 * cm, title=obj.title,
                            author='Stasiun Geofisika Kelas I Jayapura – BMKG')
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
