from rest_framework import serializers
from .models import WRSNGStatus
# import datetime # Tidak diperlukan lagi di sini

class WRSNGStatusSerializer(serializers.ModelSerializer):
    """
    Serializer untuk validasi dan representasi data WRSNGStatus.
    """
    display_status_display = serializers.CharField(source='get_display_status_display', read_only=True)
    chrome_status_display = serializers.CharField(source='get_chrome_status_display', read_only=True)

    class Meta:
        model = WRSNGStatus
        fields = [
            'id',
            'status_datetime', # DIUBAH: dari 'date'
            'wrs_code',
            'latitude',
            'longitude',
            'display_status',
            'display_status_display',
            'chrome_status',
            'chrome_status_display',
            'remark',
            # 'last_updated' dihapus
        ]
        # 'status_datetime' bisa ditulis (jika dikirim oleh client)
        # atau akan diisi otomatis oleh default=timezone.now
        read_only_fields = ['id', 'display_status_display', 'chrome_status_display']

    def validate(self, data):
        """
        Validasi kustom.
        Hanya memastikan 'wrs_code' ada.
        """
        if not data.get('wrs_code'):
            raise serializers.ValidationError("wrs_code is required.")
        
        # DIHAPUS: Logika 'date' tidak diperlukan lagi.
        # if not data.get('date'):
        #     data['date'] = datetime.date.today()
            
        return data