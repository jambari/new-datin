"""Urai nilai indeks K dari citra FMI-K-Indices-JYP (BMKG) tanpa OCR.

Grafik BMKG bertata letak tetap: sumbu K 0–9, 48 batang (6 hari × 8 slot 3 jam UTC)
dari (tanggal-6) 03:00 UTC s.d. tanggal 03:00 UTC, warna per tingkat K. Nilai K =
tinggi batang ÷ tinggi satu tingkat; batang tinggi yang tertutup logo BMKG dibaca
dari warnanya (K 4/7/8/9 punya warna sendiri). Bila tata letak berubah, parser
melempar FmiLayoutError alih-alih menebak.
"""
import datetime
from collections import Counter

from django.conf import settings
from PIL import Image

from .models import KIndexDaily

NBARS = 48
FIXED_K = {"yellow": 4, "red": 7, "magenta": 8, "purple": 9}


class FmiLayoutError(ValueError):
    """Tata letak citra tidak sesuai yang diharapkan."""


def _color(p):
    r, g, b = p[:3]
    if r > 235 and g > 235 and b > 235:
        return None                                   # latar putih
    if abs(r - g) < 20 and abs(g - b) < 20:
        return None                                   # abu-abu/hitam: grid, garis
    if g > 200 and r < 80:
        return "green"                                # K 0–3
    if r > 230 and g > 230 and b < 60:
        return "yellow"                               # K 4
    if r > 230 and 80 < g < 200 and b < 60:
        return "orange"                               # K 5–6
    if r > 230 and g < 40 and b < 40:
        return "red"                                  # K 7
    if r > 200 and g < 60 and b > 200:
        return "magenta"                              # K 8
    if r < 140 and g < 40 and b > 60:
        return "purple"                               # K 9
    return "other"


def _dark(p):
    return sum(p[:3]) < 150


def parse_k_image(fileobj, end_date):
    """Kembalikan [(waktu mulai slot UTC, K atau None)] untuk 48 slot.

    end_date: tanggal (UTC) akhir periode citra, yaitu hari pengunduhan.
    """
    im = Image.open(fileobj).convert("RGB")
    width, height = im.size
    px = im.load()

    rows = [y for y in range(height) if sum(1 for x in range(0, width, 4) if _dark(px[x, y])) > width // 8]
    if len(rows) < 2:
        raise FmiLayoutError("garis sumbu horizontal tidak ditemukan")
    y9, y0 = min(rows), max(rows) - 1               # garis K=9 dan K=0
    if y0 - y9 < 300:
        raise FmiLayoutError("area grafik terlalu kecil")

    full = [x for x in range(width)
            if sum(1 for y in range(y9, y0, 4) if _dark(px[x, y])) > (y0 - y9) // 4 * 0.97]
    groups = []
    for x in full:
        if groups and x - groups[-1][-1] <= 3:
            groups[-1].append(x)
        else:
            groups.append([x])
    lines = [g[0] for g in groups]
    if len(lines) < 4:
        raise FmiLayoutError("garis vertikal grafik tidak ditemukan")
    x0, x1 = lines[0], lines[-2]                   # sumbu kiri, tepi kanan plot (= kiri skala warna)
    bar_w = (x1 - x0) / NBARS
    # Periode mulai 03:00 UTC: garis 00:00 UTC pertama jatuh di batang ke-7.
    if not any(abs(line - (x0 + 7 * bar_w)) < 4 for line in lines):
        raise FmiLayoutError("posisi garis pergantian hari tidak sesuai")

    unit = (y0 - y9) / 9
    start = datetime.datetime.combine(end_date - datetime.timedelta(days=6), datetime.time(3))
    out = []
    for i in range(NBARS):
        xa = int(x0 + i * bar_w + bar_w * 0.3)
        xb = int(x0 + (i + 1) * bar_w - bar_w * 0.3)
        heights, colors = [], Counter()
        for x in range(xa, xb):
            y = y0 - 2
            c0 = _color(px[x, y])
            if c0 in (None, "other"):
                heights.append(0)
                continue
            colors[c0] += 1
            gap = 0
            while y > y9:
                if _color(px[x, y]) == c0:
                    gap = 0
                else:
                    gap += 1
                    if gap > 4:
                        break
                y -= 1
            heights.append(y0 - (y + gap))
        color = colors.most_common(1)[0][0] if colors else None
        if color is None:
            k = None
        elif color in FIXED_K:
            k = FIXED_K[color]
        else:
            k = int(round(sorted(heights)[len(heights) // 2] / unit))
            k = min(max(k, 0), 9)
        out.append((start + datetime.timedelta(hours=3 * i), k))
    return out


def fmi_start_date():
    value = getattr(settings, "KINDEX_FMI_START", "2026-10-03")
    return value if isinstance(value, datetime.date) else datetime.date.fromisoformat(str(value))


def image_end_date(image_obj):
    """Akhir periode citra = tanggal UTC saat diunduh (citra berakhir 03:00 UTC hari itu)."""
    t = image_obj.updated_at.astimezone(datetime.timezone.utc)
    return t.date() if t.time() >= datetime.time(3) else t.date() - datetime.timedelta(days=1)


def update_kindex_from_image(image_obj):
    """Urai satu citra K dan perbarui KIndexDaily mulai KINDEX_FMI_START.

    Nilai citra yang lebih baru menimpa nilai lama (slot terakhir sering masih sementara),
    tetapi slot kosong tidak menghapus nilai yang sudah ada. Hari sebelum batas FMI
    (data Excel) tidak disentuh. Kembalikan daftar tanggal yang diperbarui.
    """
    cutoff = fmi_start_date()
    with image_obj.image.open("rb") as f:
        slots = parse_k_image(f, image_end_date(image_obj))
    by_day = {}
    for t, k in slots:
        by_day.setdefault(t.date(), {})[t.hour // 3] = k
    updated = []
    for day, values in sorted(by_day.items()):
        if day < cutoff:
            continue
        obj, _ = KIndexDaily.objects.get_or_create(tanggal=day, defaults={"sumber": KIndexDaily.SUMBER_FMI})
        if obj.sumber != KIndexDaily.SUMBER_FMI:
            obj.k_values = []
        current = list(obj.k_values or [])
        current = (current + [None] * 8)[:8]
        for slot, k in values.items():
            if k is not None:
                current[slot] = k
        obj.k_values = current
        obj.sumber = KIndexDaily.SUMBER_FMI
        obj.keterangan = "" if any(k is not None for k in current) else "Tidak ada data"
        obj.source_file = image_obj.filename
        obj.a_index_source = None
        obj.save()
        updated.append(day)
    return updated
