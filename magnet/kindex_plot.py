"""Grafik indeks K (per 3 jam) dan A (harian) JYP dari KIndexDaily, gaya warna citra BMKG.

Dipakai halaman publik /magnetbumi/indeks-k-a/ dan kiriman Telegram harian.
"""
import datetime
import io

from .models import KIndexDaily

# Warna tingkat K seperti skala citra FMI BMKG.
K_COLORS = ['#00ff00'] * 4 + ['#ffff00', '#ffcc00', '#ff6600', '#ff0000', '#ff00ff', '#660066']

A_COLORS = {
    'Tenang': '#00c853',
    'Badai Kecil': '#ffcc00',
    'Badai Menengah': '#ff6600',
    'Badai Besar': '#ff0000',
}

BULAN = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli',
         'Agustus', 'September', 'Oktober', 'November', 'Desember']


def _tgl(d):
    return f'{d.day} {BULAN[d.month - 1]} {d.year}'


def latest_day():
    """Tanggal terakhir yang punya nilai K (sumber apa pun)."""
    for obj in KIndexDaily.objects.order_by('-tanggal')[:10]:
        if obj.has_data:
            return obj.tanggal
    return None


def _rows(end_day, days):
    start = end_day - datetime.timedelta(days=days - 1)
    found = {o.tanggal: o for o in KIndexDaily.objects.filter(tanggal__range=(start, end_day))}
    return [(start + datetime.timedelta(days=i), found.get(start + datetime.timedelta(days=i)))
            for i in range(days)]


def _figure():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    return plt


def render_k_png(end_day, days=7):
    """PNG indeks K per 3 jam untuk `days` hari berakhir di end_day (UTC)."""
    plt = _figure()
    rows = _rows(end_day, days)
    fig, ax = plt.subplots(figsize=(13, 5.2), dpi=110)
    for d, (day, obj) in enumerate(rows):
        values = (obj.k_values if obj else None) or [None] * 8
        partial = obj.partial_blocks if obj else []
        for slot, k in enumerate(values[:8]):
            if k is None:
                continue
            ax.bar(d * 8 + slot + 0.5, max(k, 0.08), width=1.0, color=K_COLORS[int(k)],
                   edgecolor='#333', linewidth=0.4, hatch='///' if slot in partial else None)
    for d in range(1, days):
        ax.axvline(d * 8, color='#111', linewidth=1.2)
    ax.set_xlim(0, days * 8)
    ax.set_ylim(0, 9)
    ax.set_yticks(range(10))
    ax.set_xticks([d * 8 for d in range(days + 1)])
    ax.set_xticklabels([f'{(rows[0][0] + datetime.timedelta(days=d)):%d-%b}' for d in range(days + 1)], fontsize=9)
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    ax.set_ylabel('Nilai Indeks K')
    ax.set_xlabel('Waktu (UTC)')
    ax.set_title(f'Indeks K Kemagnetan Bumi Per 3 Jam — Jayapura (JYP)\n'
                 f'{_tgl(rows[0][0])} s.d. {_tgl(rows[-1][0])} UTC', fontsize=12, fontweight='bold')

    legend = []
    for day, obj in rows:
        if obj and obj.has_data:
            if 'Sementara' in (obj.keterangan or ''):
                note = ' (sementara)'
            elif not obj.is_complete or obj.partial_blocks:
                note = ' (data tdk lengkap)'
            else:
                note = ''
            legend.append(f'{day:%d/%m}: A={obj.a_index:.0f} {obj.criteria_label}{note}')
    if legend:
        ax.text(1.01, 1.0, '\n'.join(legend), transform=ax.transAxes, va='top', fontsize=8.5,
                family='monospace')
    ax.text(1.01, 0.0, 'Arsir = data blok < 90%\nKosong = tidak ada data\n\n'
            'Hitung lokal metode FMI\ndari data LEMI-018 JYP\nStasiun Geofisika Jayapura',
            transform=ax.transAxes, va='bottom', fontsize=7.5, color='#555')
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    plt.close(fig)
    return buf.getvalue()


def render_a_png(end_day, days=7):
    """PNG indeks A harian untuk `days` hari berakhir di end_day."""
    plt = _figure()
    rows = _rows(end_day, days)
    fig, ax = plt.subplots(figsize=(13, 4.6), dpi=110)
    top = 30
    for i, (day, obj) in enumerate(rows):
        if not obj or obj.a_index is None:
            continue
        crit = obj.criteria_label
        ax.bar(i, obj.a_index, width=0.6, color=A_COLORS.get(crit, '#bbb'), edgecolor='#333', linewidth=0.5)
        ax.text(i, obj.a_index + 1, f'{obj.a_index:.0f}\n{crit}', ha='center', va='bottom', fontsize=8.5)
        top = max(top, obj.a_index * 1.3)
    for level in (30, 50, 100):
        if level < top:
            ax.axhline(level, color='#888', linestyle='--', linewidth=0.8)
    ax.set_ylim(0, top)
    ax.set_xticks(range(days))
    ax.set_xticklabels([f'{d:%d-%b}' for d, _ in rows])
    ax.set_ylabel('Indeks A (nT)')
    ax.set_title(f'Indeks A Harian — Jayapura (JYP)\n{_tgl(rows[0][0])} s.d. {_tgl(rows[-1][0])}',
                 fontsize=12, fontweight='bold')
    ax.grid(axis='y', linestyle='--', alpha=0.3)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    plt.close(fig)
    return buf.getvalue()
