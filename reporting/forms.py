import datetime

from django import forms

from .common import BULAN

REPORT_TYPES = [
    ("kualitas_udara", "Kualitas Udara (KAH & SPM)"),
    ("magnet_petir", "Magnetbumi & Listrik Udara"),
    ("percepatan_tanah", "Percepatan Tanah (Spectra Acceleration)"),
]
MONTHS = [(i, BULAN[i]) for i in range(1, 13)]
INPUT = "w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
MAX_MONTHS = 12


def _years():
    this = datetime.date.today().year
    return [(y, y) for y in range(this, 2004, -1)]


class ReportForm(forms.Form):
    jenis = forms.ChoiceField(choices=REPORT_TYPES, label="Jenis laporan",
                              widget=forms.Select(attrs={"class": INPUT}))
    start_bulan = forms.TypedChoiceField(choices=MONTHS, coerce=int, label="Dari bulan",
                                         widget=forms.Select(attrs={"class": INPUT}))
    start_tahun = forms.TypedChoiceField(choices=_years, coerce=int, label="Tahun",
                                         widget=forms.Select(attrs={"class": INPUT}))
    end_bulan = forms.TypedChoiceField(choices=MONTHS, coerce=int, label="Sampai bulan",
                                       widget=forms.Select(attrs={"class": INPUT}))
    end_tahun = forms.TypedChoiceField(choices=_years, coerce=int, label="Tahun",
                                       widget=forms.Select(attrs={"class": INPUT}))
    nip = forms.CharField(max_length=30, required=False, label="NIP", widget=forms.TextInput(attrs={"class": INPUT}))
    unit_kerja = forms.CharField(max_length=100, initial="Stasiun Geofisika Jayapura", label="Unit kerja",
                                 widget=forms.TextInput(attrs={"class": INPUT}))
    tempat_tanggal = forms.CharField(max_length=60, required=False, label="Tempat, tanggal tanda tangan",
                                     widget=forms.TextInput(attrs={"class": INPUT, "placeholder": "Jayapura, 5 April 2026"}))

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


class KIndexUploadForm(forms.Form):
    berkas = forms.FileField(label="Berkas Excel indeks K (.xlsx)",
                             widget=forms.ClearableFileInput(attrs={"class": INPUT, "accept": ".xlsx"}))
    tahun = forms.TypedChoiceField(choices=_years, coerce=int, label="Tahun data",
                                   widget=forms.Select(attrs={"class": INPUT}))

    def clean_berkas(self):
        f = self.cleaned_data["berkas"]
        if not f.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Berkas harus berformat .xlsx.")
        if f.size > 10 * 1024 * 1024:
            raise forms.ValidationError("Ukuran berkas maksimal 10 MB.")
        return f
