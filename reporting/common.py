"""Utilitas bersama laporan: periode bulan, nama bulan, format angka Indonesia."""
import calendar
import datetime

BULAN = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
         "Agustus", "September", "Oktober", "November", "Desember"]


class Period:
    """Rentang bulan penuh [start, end] (inklusif)."""

    def __init__(self, start_year, start_month, end_year, end_month):
        self.start = datetime.date(start_year, start_month, 1)
        self.end = datetime.date(end_year, end_month, calendar.monthrange(end_year, end_month)[1])
        if self.end < self.start:
            raise ValueError("Bulan akhir sebelum bulan awal.")

    @property
    def months(self):
        """Daftar (tahun, bulan) dalam periode."""
        out, y, m = [], self.start.year, self.start.month
        while (y, m) <= (self.end.year, self.end.month):
            out.append((y, m))
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return out

    @property
    def start_ym(self):
        return f"{self.start:%Y-%m}"

    @property
    def end_ym(self):
        return f"{self.end:%Y-%m}"

    @property
    def days(self):
        return (self.end - self.start).days + 1

    @property
    def label(self):
        a, b = self.start, self.end
        return f"{a.day} {BULAN[a.month]} {a.year} – {b.day} {BULAN[b.month]} {b.year}"

    @property
    def short_label(self):
        a, b = self.start, self.end
        if (a.year, a.month) == (b.year, b.month):
            return f"{BULAN[a.month]} {a.year}"
        if a.year == b.year:
            return f"{BULAN[a.month]} – {BULAN[b.month]} {a.year}"
        return f"{BULAN[a.month]} {a.year} – {BULAN[b.month]} {b.year}"


def month_label(year, month):
    return f"{BULAN[month]} {year}"


def fmt(value, digits=2):
    """Angka gaya Indonesia (koma desimal, titik ribuan); '–' bila kosong."""
    if value is None:
        return "–"
    if isinstance(value, int) and digits == 0:
        return f"{value:,}".replace(",", ".")
    if value != 0 and abs(value) < 10 ** -digits:
        return f"{value:.2e}".replace(".", ",")
    s = f"{value:,.{digits}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def pct(part, whole, digits=1):
    return fmt(100 * part / whole, digits) if whole else "–"
