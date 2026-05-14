# hujan/forms.py

from django import forms
from .models import Hujan
from jadwal.models import Pegawai

KATEGORI_CHOICES = [
    ('', '----- Pilih Kategori -----'),
    ('nihil', 'Nihil (0 mm)'),
    ('sangat ringan', 'Sangat Ringan (< 10 mm)'),
    ('ringan', 'Ringan (10–20 mm)'),
    ('sedang', 'Sedang (20–30 mm)'),
    ('lebat', 'Lebat (30–50 mm)'),
    ('sangat lebat', 'Sangat Lebat (> 50 mm)'),
    ('tak terukur', 'TTU (Tak Terukur)'),
]

SELECT_CLASS = 'border rounded w-full p-2 bg-white'

class HujanForm(forms.ModelForm):
    kategori = forms.ChoiceField(
        choices=KATEGORI_CHOICES,
        widget=forms.Select(attrs={'class': SELECT_CLASS}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        petugas_qs = Pegawai.objects.filter(tanggal_keluar__isnull=True)
        self.fields['petugas'] = forms.ChoiceField(
            choices=[('', '----- Pilih Petugas -----')] + [(p.nama, p.nama) for p in petugas_qs],
            widget=forms.Select(attrs={'class': SELECT_CLASS}),
        )

    class Meta:
        model = Hujan
        fields = ['tanggal', 'obs', 'hilman', 'kategori', 'petugas', 'keterangan']
        widgets = {
            'tanggal': forms.DateInput(attrs={'type': 'date', 'class': 'border rounded w-full p-2'}),
            'obs': forms.NumberInput(attrs={'class': 'border rounded w-full p-2', 'step': '0.1'}),
            'hilman': forms.NumberInput(attrs={'class': 'border rounded w-full p-2', 'step': '0.1'}),
            'keterangan': forms.Textarea(attrs={'class': 'border rounded w-full p-2', 'rows': 3}),
        }