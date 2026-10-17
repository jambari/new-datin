import re

from django import forms

from .models import KAHSeriesData, SPMSeriesData

SELECT_CLASS = "border rounded w-full p-2 bg-white"


class KAHSeriesDataForm(forms.ModelForm):
    class Meta:
        model = KAHSeriesData
        fields = [
            "stasiun",
            "bulan",
            "minggu",
            "ph",
            "dh",
            "ca",
            "mg",
            "na",
            "k",
            "nh4",
            "cl",
            "so4",
            "no3",
            "kt",
            "ac",
            "al",
            "ch",
            "ox",
        ]
        widgets = {
            "stasiun": forms.TextInput(attrs={"class": "border rounded w-full p-2"}),
            # Teks biasa (bukan type="month") agar bisa diisi di Firefox.
            "bulan": forms.TextInput(
                attrs={
                    "class": "border rounded w-full p-2",
                    "placeholder": "YYYY-MM, contoh 2026-01",
                    "pattern": r"\d{4}-(0[1-9]|1[0-2])",
                    "title": "Format YYYY-MM, contoh 2026-01",
                }
            ),
            "minggu": forms.TextInput(attrs={"class": "border rounded w-full p-2", "maxlength": "2"}),
            "ph": forms.NumberInput(attrs={"class": "border rounded w-full p-2", "step": "0.01"}),
            "dh": forms.NumberInput(attrs={"class": "border rounded w-full p-2", "step": "0.01"}),
            "ca": forms.NumberInput(attrs={"class": "border rounded w-full p-2", "step": "0.01"}),
            "mg": forms.NumberInput(attrs={"class": "border rounded w-full p-2", "step": "0.01"}),
            "na": forms.NumberInput(attrs={"class": "border rounded w-full p-2", "step": "0.01"}),
            "k": forms.NumberInput(attrs={"class": "border rounded w-full p-2", "step": "0.01"}),
            "nh4": forms.NumberInput(attrs={"class": "border rounded w-full p-2", "step": "0.01"}),
            "cl": forms.NumberInput(attrs={"class": "border rounded w-full p-2", "step": "0.01"}),
            "so4": forms.NumberInput(attrs={"class": "border rounded w-full p-2", "step": "0.01"}),
            "no3": forms.NumberInput(attrs={"class": "border rounded w-full p-2", "step": "0.01"}),
            "kt": forms.NumberInput(attrs={"class": "border rounded w-full p-2", "step": "0.01"}),
            "ac": forms.NumberInput(attrs={"class": "border rounded w-full p-2", "step": "0.01"}),
            "al": forms.NumberInput(attrs={"class": "border rounded w-full p-2", "step": "0.01"}),
            "ch": forms.NumberInput(attrs={"class": "border rounded w-full p-2", "step": "0.01"}),
            "ox": forms.NumberInput(attrs={"class": "border rounded w-full p-2", "step": "0.01"}),
        }

    def clean_bulan(self):
        value = self.cleaned_data.get("bulan", "")
        value = value.strip() if value else ""
        if value and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
            raise forms.ValidationError("Format bulan harus YYYY-MM, contoh 2005-01.")
        return value


class SPMSeriesDataForm(forms.ModelForm):
    class Meta:
        model = SPMSeriesData
        fields = ["stasiun", "timestamp", "spm"]
        widgets = {
            "stasiun": forms.TextInput(attrs={"class": "border rounded w-full p-2"}),
            "timestamp": forms.DateInput(attrs={"type": "date", "class": "border rounded w-full p-2"}),
            "spm": forms.NumberInput(attrs={"class": "border rounded w-full p-2", "step": "0.01"}),
        }
