from django.contrib import admin
from .models import WRSNGStatus

@admin.register(WRSNGStatus)
class WRSNGStatusAdmin(admin.ModelAdmin):
    """
    Kustomisasi tampilan WRSNGStatus di panel Admin Django.
    Diperbarui untuk menggunakan status_datetime.
    """
    
    # Menampilkan field-field utama di daftar
    list_display = (
        'status_datetime', # DIUBAH: dari 'date'
        'wrs_code', 
        'display_status', 
        'chrome_status', 
        'latitude', 
        'longitude',
        'remark',
    )
    
    # Menambahkan filter di sidebar
    list_filter = (
        'status_datetime', # DIUBAH: dari 'date'
        'wrs_code', 
        'display_status', 
        'chrome_status'
    )
    
    # Menambahkan fungsionalitas pencarian
    search_fields = ('wrs_code', 'remark')
    
    # Mengurutkan berdasarkan timestamp terbaru
    ordering = ('-status_datetime', 'wrs_code') # DIUBAH: dari '-date'
    
    # Membuat 'status_datetime' read-only di halaman detail admin
    # karena idealnya diatur oleh sistem saat data masuk.
    readonly_fields = ('status_datetime',)

