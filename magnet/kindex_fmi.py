"""Indeks K metode FMI (Sucksdorff, Pirjola & Häkkinen 1991) dari data mentah LEMI-018 JYP.

Port dari kode C resmi FMI (space.fmi.fi/MAGN/K-index/FMI_method/K_index.h), mengikuti
port Python di MagPy (magpy/core/activity.py, lisensi BSD), divektorkan dengan numpy:

1. K sementara dari rentang (maks - min) X dan Y tiap blok 3 jam UTC.
2. Rata-rata per jam dengan jendela diperlebar ±(30 menit + n + K^3.3 menit); n = 90 menit
   malam, 60 menit fajar/senja, 0 siang (waktu lokal dari bujur).
3. Kurva hari tenang Sr = deret Fourier orde 5 dari 24 rata-rata jam tersebut.
4. K dari rentang (data - Sr). Langkah 2-4 diulang sekali lagi (total 3 kali hitung K).

Satu hari dihitung dengan data hari sebelum & sesudahnya (jendela bisa sampai ±24 jam).
Tanpa data hari sesudahnya, nilai jam-jam terakhir bersifat sementara.
"""
import datetime
import math
from pathlib import Path

import numpy as np

# Batas bawah kelas K sebagai pecahan L9 (tabel standar IAGA, DefLimit/7500 di kode FMI).
K_SCALE = np.array([0.01, 0.02, 0.04, 0.08, 0.14, 0.24, 0.40, 0.66, 1.0])
HARM_ORDER = 5
K_EXPONENT = 3.3
MAX_GAP_MIN = 15             # celah < 15 menit diinterpolasi linear
MIN_PER_DAY = 1440
MIN_SECONDS_PER_MINUTE = 30  # nilai menit butuh >= 30 sampel 1 detik
STEP_JUMP_NT = 100           # loncatan antar menit di atas ini = buatan (bukan geomagnet)
STEP_JOIN_MIN = 60
STEP_REF_MIN = 10
# Beda level melintasi celah data, setelah perubahan harian dikeluarkan. Dari 82 celah nyata
# (Okt 2025 - Okt 2026) terbesar 100 nT; di atas ini dianggap sensor bergeser, bukan geomagnet.
GAP_LEVEL_NT = 150
GAP_MIN_POINTS = 5
PARTIAL_COVERAGE = 90        # persen menit: di bawah ini blok/hari ditandai tidak lengkap

JYP_LONGITUDE = 140.7


def read_lemi_raw(path):
    """Baca berkas mentah LEMI-018 (1 detik): kembalikan (detik UTC sejak epoch, X, Y) dalam nT."""
    data = np.genfromtxt(path, usecols=range(9), dtype=float, invalid_raise=False)
    if data.size == 0:
        return np.empty(0), np.empty(0), np.empty(0)
    data = np.atleast_2d(data)
    data = data[~np.isnan(data).any(axis=1)]
    years, months, days, hh, mm, ss = (data[:, i].astype(int) for i in range(6))
    days_since_epoch = (np.array([datetime.date(y, m, d).toordinal() for y, m, d in zip(years, months, days)])
                        - datetime.date(1970, 1, 1).toordinal())
    t = days_since_epoch * 86400 + hh * 3600 + mm * 60 + ss
    return t, data[:, 6], data[:, 7]


def minute_means(t, x, y, start, minutes):
    """Nilai 1 menit pada grid [start, start + minutes): median 60 sampel 1 detik.

    Median (bukan rata-rata) supaya lonjakan sesaat LEMI (bisa ribuan nT selama beberapa
    detik) tidak ikut menaikkan rentang K. Menit dengan < 30 sampel = NaN.
    """
    rel = t - start
    ok = (rel >= 0) & (rel < minutes * 60)
    rel = rel[ok].astype(int)
    out = []
    for comp in (x[ok], y[ok]):
        grid = np.full(minutes * 60, np.nan)
        grid[rel] = comp
        grid = grid.reshape(minutes, 60)
        count = np.count_nonzero(~np.isnan(grid), axis=1)
        with np.errstate(all="ignore"):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                med = np.nanmedian(grid, axis=1)
        med[count < MIN_SECONDS_PER_MINUTE] = np.nan
        out.append(med)
    return out[0], out[1]


def remove_steps(a, jump=STEP_JUMP_NT, join=STEP_JOIN_MIN, ref=STEP_REF_MIN):
    """Buang loncatan baseline buatan (perawatan sensor, ganti offset) dari data menit.

    Lonjakan > `jump` nT antar menit tidak terjadi secara alami di lintang rendah. Lonjakan
    yang berdekatan (< `join` menit) dianggap satu gangguan: rentang itu dikosongkan, lalu
    data sesudahnya digeser supaya medianya sama dengan median `ref` menit sebelumnya.
    Kembalikan (array terkoreksi, daftar (indeks awal, indeks akhir, geseran nT)).
    """
    a = np.asarray(a, float).copy()
    valid = np.flatnonzero(~np.isnan(a))
    if len(valid) < 2:
        return a, []
    # Hanya data bersambung; beda melintasi celah panjang dinilai di level_across_gaps().
    steps_between = np.diff(valid)
    big = valid[1:][(np.abs(np.diff(a[valid])) > jump) & (steps_between <= ref)]
    clusters = []
    for i in big:
        if clusters and i - clusters[-1][1] <= join:
            clusters[-1][1] = i
        else:
            clusters.append([i, i])
    steps = []
    for start, end in clusters:
        start = max(start - 1, 0)
        before = a[max(start - ref, 0):start]
        after = a[end + 1:end + 1 + ref]
        a[start:end + 1] = np.nan
        if np.isnan(before).all() or np.isnan(after).all():
            continue
        shift = np.nanmedian(before) - np.nanmedian(after)
        a[end + 1:] += shift
        steps.append((start, end, float(shift)))
    return a, steps


def _edge_median(a, start, stop):
    seg = a[max(start, 0):max(stop, 0)]
    return float(np.nanmedian(seg)) if np.count_nonzero(~np.isnan(seg)) >= GAP_MIN_POINTS else None


def level_across_gaps(a, threshold=GAP_LEVEL_NT, ref=STEP_REF_MIN):
    """Samakan level bila sensor bergeser selama celah data (mis. saat program LEMI mati).

    Beda median sebelum & sesudah celah dikurangi perubahan wajar pada jam yang sama di hari
    lain dalam array. Selisih di bawah `threshold` dibiarkan: itu variasi geomagnet.
    Kembalikan (array, daftar (indeks awal celah, indeks akhir celah, geseran nT)).
    """
    a = np.asarray(a, float).copy()
    valid = np.flatnonzero(~np.isnan(a))
    if len(valid) < 2:
        return a, []
    steps = []
    for k in np.flatnonzero(np.diff(valid) > ref):
        last, first = int(valid[k]), int(valid[k + 1])
        before = _edge_median(a, last - ref + 1, last + 1)
        after = _edge_median(a, first, first + ref)
        if before is None or after is None:
            continue
        expected = []
        for day in (-2, -1, 1, 2):
            off = day * MIN_PER_DAY
            if last - ref + 1 + off < 0 or first + ref + off > len(a):
                continue
            b2 = _edge_median(a, last - ref + 1 + off, last + 1 + off)
            a2 = _edge_median(a, first + off, first + ref + off)
            if b2 is not None and a2 is not None:
                expected.append(a2 - b2)
        change = (after - before) - (float(np.median(expected)) if expected else 0.0)
        if abs(change) > threshold:
            a[first:] -= change
            steps.append((last + 1, first - 1, -change))
    return a, steps


def correct_levels(a):
    """Loncatan pada data bersambung lalu pergeseran melintasi celah: (array, semua koreksi)."""
    a, jumps = remove_steps(a)
    a, gaps = level_across_gaps(a)
    return a, jumps + gaps


def fill_gaps(a, max_gap=MAX_GAP_MIN):
    """Interpolasi linear celah NaN yang lebih pendek dari max_gap menit (di antara dua nilai)."""
    a = a.copy()
    nan = np.isnan(a)
    i, n = 0, len(a)
    while i < n:
        if not nan[i]:
            i += 1
            continue
        j = i
        while j < n and nan[j]:
            j += 1
        if i > 0 and j < n and (j - i) < max_gap:
            a[i:j] = np.linspace(a[i - 1], a[j], j - i + 2)[1:-1]
        i = j
    return a


def k_limits(l9):
    return K_SCALE * l9


def _k_from_ranges(day_x, day_y, limits):
    """K tiap blok 3 jam (8 nilai) dari rentang terbesar X/Y; -1 kalau datanya kurang."""
    ks = []
    for b in range(8):
        sx = day_x[b * 180:(b + 1) * 180]
        sy = day_y[b * 180:(b + 1) * 180]
        if np.count_nonzero(~np.isnan(sx)) < 90 or np.count_nonzero(~np.isnan(sy)) < 90:
            ks.append(-1)
            continue
        r = max(np.nanmax(sx) - np.nanmin(sx), np.nanmax(sy) - np.nanmin(sy))
        ks.append(int(np.searchsorted(limits, r, side="left")))   # r <= limit[i] -> K=i
    return ks


def _default_lengths(longitude):
    """Tambahan jendela n (menit) per jam UTC menurut waktu lokal."""
    by_local = [90] * 3 + [60] * 3 + [0] * 12 + [60] * 3 + [90] * 3
    shift = int(longitude // 15)
    return [by_local[(h + shift) % 24] for h in range(24)]


def _hour_means(arr3, ks, def_len):
    """Rata-rata jam hari tengah dengan jendela ±(30 + n + K^3.3) menit; celah diinterpolasi."""
    means = np.full(24, np.nan)
    for h in range(24):
        k = ks[h // 3]
        wing = 30 + def_len[h] + (min(int(math.exp(K_EXPONENT * math.log(k))), 18 * 60) if k > 0 else 0)
        wing = min(wing, 24 * 60)
        mid = MIN_PER_DAY + 60 * h + 30
        seg = arr3[mid - wing:mid + wing + 1]
        if len(seg) == 2 * wing + 1 and not np.isnan(seg).any():
            means[h] = seg.mean()
    good = ~np.isnan(means)
    if not good.any():
        return None
    hours = np.arange(24)
    return np.interp(hours, hours[good], means[good])      # ujung diisi konstan, seperti FMI


def _harmonic_fit(means):
    """Sr per menit hari tengah: Fourier orde 5 dari 24 rata-rata jam setelah tren dibuang."""
    t0, t1 = 30 * 60, 23 * 3600 + 30 * 60
    th = t0 + 3600 * np.arange(24)
    coeff = (means[23] - means[0]) / (t1 - t0)
    detr = means - coeff * (th - t0)
    k = np.arange(HARM_ORDER + 1)[:, None]
    ang = -k * (2 * np.pi / 24) * np.arange(24)[None, :]
    re = (detr * np.cos(ang)).sum(axis=1)
    im = (detr * np.sin(ang)).sum(axis=1)
    t = np.arange(MIN_PER_DAY) * 60.0
    angle2 = (t - t0) * (2 * np.pi * (23 / 24) / (t1 - t0))
    out = np.full(MIN_PER_DAY, re[0])
    for kk in range(1, HARM_ORDER + 1):
        out += 2 * (re[kk] * np.cos(kk * angle2) - im[kk] * np.sin(kk * angle2))
    return out / 24 + coeff * (t - t0)


def k_fmi_day(x3, y3, l9, longitude=JYP_LONGITUDE):
    """Hitung 8 nilai K hari tengah dari array menit 3 hari (4320 nilai X & Y, NaN = kosong).

    Kembalikan (k_values, sr_x, sr_y); k_values berisi None untuk blok tanpa data.
    """
    limits = k_limits(l9)
    x3, _ = correct_levels(x3)
    y3, _ = correct_levels(y3)
    x3, y3 = fill_gaps(x3), fill_gaps(y3)
    day = slice(MIN_PER_DAY, 2 * MIN_PER_DAY)
    def_len = _default_lengths(longitude)

    ks = _k_from_ranges(x3[day], y3[day], limits)
    sr_x = sr_y = None
    for _ in range(2):
        mx, my = _hour_means(x3, ks, def_len), _hour_means(y3, ks, def_len)
        if mx is None or my is None:
            break
        sr_x, sr_y = _harmonic_fit(mx), _harmonic_fit(my)
        ks = _k_from_ranges(x3[day] - sr_x, y3[day] - sr_y, limits)
    return [k if k >= 0 else None for k in ks], sr_x, sr_y


def raw_files_for(raw_dir, day):
    """Berkas mentah LEMI untuk satu tanggal UTC ('YYYY MM DD hh mm ss.txt', bisa lebih dari satu)."""
    return sorted(Path(raw_dir).glob(f"{day:%Y %m %d} *.txt"))


def load_three_days(raw_dir, day):
    """Array menit X & Y untuk (day-1, day, day+1) dari folder data mentah LEMI."""
    start_day = day - datetime.timedelta(days=1)
    start = (start_day.toordinal() - datetime.date(1970, 1, 1).toordinal()) * 86400
    ts, xs, ys = [], [], []
    for offset in range(3):
        for path in raw_files_for(raw_dir, start_day + datetime.timedelta(days=offset)):
            t, x, y = read_lemi_raw(path)
            ts.append(t)
            xs.append(x)
            ys.append(y)
    if not ts:
        nan = np.full(3 * MIN_PER_DAY, np.nan)
        return nan, nan.copy()
    return minute_means(np.concatenate(ts), np.concatenate(xs), np.concatenate(ys), start, 3 * MIN_PER_DAY)


def next_day_missing(x3, y3):
    """Data hari sesudah hari tengah belum ada separuhnya."""
    nxt = slice(2 * MIN_PER_DAY, 3 * MIN_PER_DAY)
    have = np.count_nonzero(~np.isnan(x3[nxt]) & ~np.isnan(y3[nxt]))
    return have < MIN_PER_DAY // 2


def block_coverage(x3, y3):
    """Persen menit berisi data per blok 3 jam hari tengah (X dan Y sama-sama ada)."""
    both = ~np.isnan(x3[MIN_PER_DAY:2 * MIN_PER_DAY]) & ~np.isnan(y3[MIN_PER_DAY:2 * MIN_PER_DAY])
    return [int(round(100 * np.count_nonzero(both[b * 180:(b + 1) * 180]) / 180)) for b in range(8)]


def compute_day(day, raw_dir=None, l9=None):
    """Hitung indeks K JYP untuk satu tanggal UTC dari data mentah. Kembalikan dict hasil."""
    from django.conf import settings

    raw_dir = raw_dir or settings.LEMI_RAW_DIR
    l9 = l9 or settings.KINDEX_JYP_L9
    x3, y3 = load_three_days(raw_dir, day)
    _, steps_x = correct_levels(x3)
    _, steps_y = correct_levels(y3)
    ks, _, _ = k_fmi_day(x3, y3, l9)
    coverage = block_coverage(x3, y3)
    missing_next = next_day_missing(x3, y3)
    # Hari sesudahnya belum tiba = sementara; sudah lewat tapi kosong tidak akan berubah sendiri.
    today = datetime.datetime.now(datetime.timezone.utc).date()
    provisional = missing_next and day + datetime.timedelta(days=1) >= today
    return {
        "tanggal": day,
        "k_values": ks,
        "coverage": coverage,
        "provisional": provisional,
        "next_day_absent": missing_next and not provisional,
        "steps": len(steps_x) + len(steps_y),
        "files": [p.name for p in raw_files_for(raw_dir, day)],
    }


def store_day(day, raw_dir=None, l9=None):
    """Hitung lalu simpan ke KIndexDaily (sumber lokal). Hari data Excel tidak disentuh.

    Kembalikan (hasil, obj) — obj None kalau hari itu tidak disimpan.
    """
    from .fmi_kindex import fmi_start_date
    from .models import KIndexDaily

    result = compute_day(day, raw_dir, l9)
    if day < fmi_start_date() or not any(k is not None for k in result["k_values"]):
        return result, None
    obj, _ = KIndexDaily.objects.get_or_create(tanggal=day, defaults={"sumber": KIndexDaily.SUMBER_LOKAL})
    obj.k_values = result["k_values"]
    obj.k_coverage = result["coverage"]
    obj.sumber = KIndexDaily.SUMBER_LOKAL
    notes = []
    if result["provisional"]:
        notes.append("Sementara")
    percent = sum(result["coverage"]) // 8
    if percent < PARTIAL_COVERAGE:
        notes.append(f"Data tidak lengkap ({percent}%)")
    if result["next_day_absent"]:
        notes.append("Data hari berikutnya tidak ada")
    if result["steps"]:
        notes.append(f"{result['steps']} loncatan dikoreksi")
    obj.keterangan = ", ".join(notes)
    obj.source_file = ", ".join(result["files"])[:255]
    obj.a_index_source = None
    obj.save()
    return result, obj
