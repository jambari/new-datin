from django import forms
from .models import Logbook
from django.contrib.auth.models import User

class LogbookForm(forms.ModelForm):
    class Meta:
        model = Logbook
        fields = [
            'shift', 
            'status_absen',       
            'petugas_sebelum',    
            'petugas_selanjutnya',
            'seiscomp_seismik', 
            'seiscomp_accelero', 
            'esdx', 
            'petir', 
            'lemi', 
            'proton', 
            'catatan'
        ]
        widgets = {
            'shift': forms.Select(attrs={'class': 'w-full p-2 border border-gray-300 rounded-md'}),
            'status_absen': forms.Select(attrs={'class': 'w-full p-2 border border-gray-300 rounded-md', 'id': 'id_status_absen'}),
            'petugas_sebelum': forms.Select(attrs={'class': 'w-full p-2 border border-gray-300 rounded-md'}),
            'petugas_selanjutnya': forms.Select(attrs={'class': 'w-full p-2 border border-gray-300 rounded-md'}),
            'seiscomp_seismik': forms.Select(attrs={'class': 'w-full p-2 border border-gray-300 rounded-md'}),
            'seiscomp_accelero': forms.Select(attrs={'class': 'w-full p-2 border border-gray-300 rounded-md'}),
            'esdx': forms.Select(attrs={'class': 'w-full p-2 border border-gray-300 rounded-md'}),
            'petir': forms.Select(attrs={'class': 'w-full p-2 border border-gray-300 rounded-md'}),
            'lemi': forms.Select(attrs={'class': 'w-full p-2 border border-gray-300 rounded-md'}),
            'proton': forms.Select(attrs={'class': 'w-full p-2 border border-gray-300 rounded-md'}),
            'catatan': forms.Textarea(attrs={'class': 'w-full p-2 border border-gray-300 rounded-md', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super(LogbookForm, self).__init__(*args, **kwargs)
        
        # --- LOGIC FILTER GROUP OPERASIONAL ---
        # Hanya ambil user yang tergabung dalam group bernama 'operasional'
        # Pastikan nama group di Admin Panel persis 'operasional' (huruf kecil semua sesuai screenshot)
        operational_users = User.objects.filter(groups__name='operasional').order_by('first_name')
        
        self.fields['petugas_sebelum'].queryset = operational_users
        self.fields['petugas_selanjutnya'].queryset = operational_users
        
        # Format tampilan nama di dropdown (Nama Depan + Belakang, atau Username jika kosong)
        self.fields['petugas_sebelum'].label_from_instance = lambda obj: (f"{obj.first_name} {obj.last_name}" if obj.first_name else obj.username).title()
        self.fields['petugas_selanjutnya'].label_from_instance = lambda obj: (f"{obj.first_name} {obj.last_name}" if obj.first_name else obj.username).title()