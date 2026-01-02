from django import forms
from .models import Logbook
from django.contrib.auth.models import User

class LogbookForm(forms.ModelForm):
    class Meta:
        model = Logbook
        fields = [
            'shift', 'status_absen', 'petugas_sebelum', 'petugas_selanjutnya',
            'hv_counter_hour', 'hv_flow_rate', 'hv_berat_kertas','hv_jam_pasang', 'hv_jam_angkat',
            'seiscomp_seismik', 'seiscomp_accelero', 'esdx', 'petir', 'lemi', 'proton', 'catatan'
        ]
        widgets = {
            'shift': forms.Select(attrs={'class': 'form-control'}),
            'status_absen': forms.Select(attrs={'class': 'form-control', 'id': 'id_status_absen'}),
            'petugas_sebelum': forms.CheckboxSelectMultiple(),
            'petugas_selanjutnya': forms.CheckboxSelectMultiple(),
            'hv_counter_hour': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
            'hv_flow_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
            'hv_berat_kertas': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
            'hv_jam_pasang': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'hv_jam_angkat': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'seiscomp_seismik': forms.Select(attrs={'class': 'form-control'}),
            'seiscomp_accelero': forms.Select(attrs={'class': 'form-control'}),
            'esdx': forms.Select(attrs={'class': 'form-control'}),
            'petir': forms.Select(attrs={'class': 'form-control'}),
            'lemi': forms.Select(attrs={'class': 'form-control'}),
            'proton': forms.Select(attrs={'class': 'form-control'}),
            'catatan': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super(LogbookForm, self).__init__(*args, **kwargs)
        operational_users = User.objects.filter(groups__name='operasional').order_by('first_name')
        self.fields['petugas_sebelum'].queryset = operational_users
        self.fields['petugas_selanjutnya'].queryset = operational_users
        
        display_name = lambda obj: (f"{obj.first_name} {obj.last_name}" if obj.first_name else obj.username).title()
        self.fields['petugas_sebelum'].label_from_instance = display_name
        self.fields['petugas_selanjutnya'].label_from_instance = display_name