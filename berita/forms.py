import re

from django import forms

from .models import Berita
from .sanitize import clean_html


class BeritaForm(forms.ModelForm):
    class Meta:
        model = Berita
        fields = ['title', 'slug', 'excerpt', 'cover', 'content', 'status']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'berita-input'}),
            'slug': forms.TextInput(attrs={'class': 'berita-input'}),
            'excerpt': forms.Textarea(attrs={'class': 'berita-input', 'rows': 3}),
            'content': forms.Textarea(attrs={
                'class': 'berita-content-input',
                'style': 'display:none',
                'id': 'id_content',
            }),
            'status': forms.Select(attrs={'class': 'berita-input'}),
        }

    def clean_content(self):
        html = self.cleaned_data.get('content', '')
        cleaned = clean_html(html)
        text = re.sub(r'<[^>]+>', '', cleaned)
        text = text.replace('&nbsp;', ' ').strip()
        if not text:
            raise forms.ValidationError('Isi berita tidak boleh kosong.')
        return cleaned
