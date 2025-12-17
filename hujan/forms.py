# hujan/forms.py

from django import forms
from .models import Hujan

class HujanForm(forms.ModelForm):
    class Meta:
        model = Hujan
        fields = ['tanggal', 'obs', 'hilman', 'kategori', 'petugas', 'keterangan']
        widgets = {
            'tanggal': forms.DateInput(attrs={'type': 'date', 'class': 'border rounded w-full p-2'}),
            'obs': forms.NumberInput(attrs={'class': 'border rounded w-full p-2', 'step': '0.1'}),
            'hilman': forms.NumberInput(attrs={'class': 'border rounded w-full p-2', 'step': '0.1'}),
            'kategori': forms.TextInput(attrs={'class': 'border rounded w-full p-2'}),
            'petugas': forms.TextInput(attrs={'class': 'border rounded w-full p-2'}),
            'keterangan': forms.Textarea(attrs={'class': 'border rounded w-full p-2', 'rows': 3}),
        }