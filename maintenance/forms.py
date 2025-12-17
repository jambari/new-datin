from django import forms
from .models import Instrument, Issue

class NativeCSSFormMixin:
    """
    Mixin untuk menyuntikkan Style CSS standar (bukan Tailwind)
    agar form langsung rapi tanpa perlu build CSS.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            # Style standar untuk input text, select, dll
            common_style = "width: 100%; padding: 8px 12px; margin-bottom: 10px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box;"
            
            # Jika Checkbox, ukurannya beda
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'style': 'transform: scale(1.2); margin-right: 10px;'})
            else:
                field.widget.attrs.update({'style': common_style})

class InstrumentForm(NativeCSSFormMixin, forms.ModelForm):
    class Meta:
        model = Instrument
        fields = ['nama_alat', 'jenis', 'merk_tipe', 'lokasi', 'shelter', 'status']

class IssueForm(NativeCSSFormMixin, forms.ModelForm):
    class Meta:
        model = Issue
        fields = ['instrument', 'judul', 'kategori', 'deskripsi', 'prioritas', 'status', 'pic']
        widgets = {
            'deskripsi': forms.Textarea(attrs={'rows': 4}),
        }