# repository/serializers.py
from rest_framework import serializers
from .models import DataAvailability, AcceleroDataAvailability
from .models import Gempa

class DataAvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = DataAvailability
        fields = ['station', 'channel', 'date', 'percentage']

class AcceleroDataAvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = AcceleroDataAvailability
        fields = ['station', 'channel', 'date', 'percentage']

class GempaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Gempa
        # Tentukan semua field yang ingin Anda terima melalui API
        fields = [
            'source_id', 'station_code', 'origin_datetime', 'latitude', 
            'longitude', 'magnitudo', 'depth', 'remark', 'felt', 'impact'
        ]
