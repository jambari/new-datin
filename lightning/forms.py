# lightning/forms.py
from django import forms

# 1. Buat Custom Widget
class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class NexStormUploadForm(forms.Form):
    csv_file = forms.FileField(
        label="Select Lightning Data (.csv)",
        help_text="Pilih maksimal 7 file sekaligus (Format: YYYYMMDD.csv).",
        # 2. Gunakan Custom Widget tersebut di sini
        widget=MultipleFileInput(attrs={
            'class': 'form-control', 
            'accept': '.csv',
            'multiple': True 
        })
    )