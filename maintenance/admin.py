from django.contrib import admin
from .models import Instrument, Issue, ActionLog

class ActionLogInline(admin.TabularInline):
    model = ActionLog
    extra = 1
    readonly_fields = ('tanggal', 'oleh') 
    # Field 'oleh' otomatis diisi via save_formset di parent

@admin.register(Instrument)
class InstrumentAdmin(admin.ModelAdmin):
    # PERBAIKAN: 'status' harus ada di list_display agar bisa diedit
    list_display = ('nama_alat', 'shelter', 'jenis', 'lokasi', 'status') 
    list_filter = ('status', 'jenis', 'shelter')
    search_fields = ('nama_alat', 'shelter', 'lokasi')
    list_editable = ('status',) # Ini memunculkan dropdown ganti status di halaman depan
    list_per_page = 20

@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ('judul', 'instrument', 'prioritas', 'status', 'pic', 'tanggal_lapor')
    list_filter = ('status', 'prioritas', 'kategori')
    search_fields = ('judul', 'instrument__nama_alat', 'instrument__shelter')
    inlines = [ActionLogInline] 
    
    # Logic otomatis mengisi user penginput log
    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            # Cek jika instance adalah ActionLog dan user belum ada
            if isinstance(instance, ActionLog) and not instance.oleh:
                instance.oleh = request.user
            instance.save()
        formset.save_m2m()