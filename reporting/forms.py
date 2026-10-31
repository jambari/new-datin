import datetime

from django import forms

from .common import BULAN

REPORT_TYPES = [
    ("kualitas_udara", "Kualitas Udara (KAH & SPM)"),
    ("magnet_petir", "Magnetbumi & Listrik Udara"),
    ("percepatan_tanah", "Percepatan Tanah (Spectra Acceleration)"),
    ("hujan", "Hujan (Curah Hujan Harian)"),
    ("gempabumi", "Gempabumi (Informasi yang Dianalisis & Disebarkan)"),
    ("gempabumi_cepat", "Gempabumi M < 5,0 (Disampaikan < 3 Menit)"),
    ("tanda_waktu", "Tanda Waktu (Terbit & Terbenam Matahari)"),
]
MONTHS = [(i, BULAN[i]) for i in range(1, 13)]
INPUT = "w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
MAX_MONTHS = 12


MAX_DAYS = 366


def _years():
    this = datetime.date.today().year
    return [(y, y) for y in range(this, 2004, -1)]


class PeriodForm(forms.Form):
    """Rentang bulan penuh, maksimal MAX_MONTHS bulan."""
    start_bulan = forms.TypedChoiceField(choices=MONTHS, coerce=int, label="Dari bulan",
                                         widget=forms.Select(attrs={"class": INPUT}))
    start_tahun = forms.TypedChoiceField(choices=_years, coerce=int, label="Tahun",
                                         widget=forms.Select(attrs={"class": INPUT}))
    end_bulan = forms.TypedChoiceField(choices=MONTHS, coerce=int, label="Sampai bulan",
                                       widget=forms.Select(attrs={"class": INPUT}))
    end_tahun = forms.TypedChoiceField(choices=_years, coerce=int, label="Tahun",
                                       widget=forms.Select(attrs={"class": INPUT}))

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        start = (data["start_tahun"], data["start_bulan"])
        end = (data["end_tahun"], data["end_bulan"])
        if end < start:
            raise forms.ValidationError("Bulan akhir tidak boleh sebelum bulan awal.")
        n = (end[0] - start[0]) * 12 + end[1] - start[1] + 1
        if n > MAX_MONTHS:
            raise forms.ValidationError(f"Periode laporan maksimal {MAX_MONTHS} bulan.")
        return data


class DateRangeForm(forms.Form):
    """Rentang tanggal dd/mm/yyyy, maksimal MAX_DAYS hari."""
    FORMATS = ["%d/%m/%Y", "%d-%m-%Y", "%d%m%Y", "%Y-%m-%d"]
    _attrs = {"class": INPUT + " w-32", "placeholder": "dd/mm/yyyy", "inputmode": "numeric",
              "autocomplete": "off", "maxlength": "10", "data-date-text": "",
              "style": "color:#111827;background:#fff"}
    start = forms.DateField(input_formats=FORMATS, label="Dari tanggal", widget=forms.TextInput(attrs=_attrs),
                            error_messages={"invalid": "Tanggal harus berformat dd/mm/yyyy.", "required": "Tanggal wajib diisi."})
    end = forms.DateField(input_formats=FORMATS, label="Sampai tanggal", widget=forms.TextInput(attrs=_attrs),
                          error_messages={"invalid": "Tanggal harus berformat dd/mm/yyyy.", "required": "Tanggal wajib diisi."})

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        if data["end"] < data["start"]:
            raise forms.ValidationError("Tanggal akhir tidak boleh sebelum tanggal awal.")
        if (data["end"] - data["start"]).days + 1 > MAX_DAYS:
            raise forms.ValidationError(f"Periode maksimal {MAX_DAYS} hari.")
        return data


class ReportForm(PeriodForm):
    jenis = forms.ChoiceField(choices=REPORT_TYPES, label="Jenis laporan",
                              widget=forms.Select(attrs={"class": INPUT}))
    nip = forms.CharField(max_length=30, required=False, label="NIP", widget=forms.TextInput(attrs={"class": INPUT}))

    field_order = ["jenis", "start_bulan", "start_tahun", "end_bulan", "end_tahun", "nip"]
