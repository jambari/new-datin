from django import template

register = template.Library()

_HARI = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu']
_BULAN = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
          'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']

@register.filter
def tanggal_indo(value):
    """Format a date object as Indonesian: 'Senin, 08 Mei 2026'"""
    if not value:
        return '—'
    try:
        hari  = _HARI[value.weekday()]
        bulan = _BULAN[value.month]
        return f"{hari}, {value.day:02d} {bulan} {value.year}"
    except Exception:
        return str(value)


_FASE = [
    (0.0625, 'Bulan Baru',       '🌑'),
    (0.1875, 'Sabit Awal',       '🌒'),
    (0.3125, 'Kuartal Pertama',  '🌓'),
    (0.4375, 'Cembung Tumbuh',   '🌔'),
    (0.5625, 'Bulan Purnama',    '🌕'),
    (0.6875, 'Cembung Susut',    '🌖'),
    (0.8125, 'Kuartal Ketiga',   '🌗'),
    (0.9375, 'Sabit Akhir',      '🌘'),
    (1.0001, 'Bulan Baru',       '🌑'),
]

@register.filter
def fase_bulan(value):
    """Return Indonesian moon phase name + emoji from fractional illumination (0–1)."""
    if value is None:
        return '—'
    try:
        f = float(value)
        for threshold, nama, ikon in _FASE:
            if f < threshold:
                return f"{ikon} {nama}"
        return '🌑 Bulan Baru'
    except Exception:
        return '—'
