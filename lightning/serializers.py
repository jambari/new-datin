# lightning/serializers.py
from rest_framework import serializers
from .models import Strike

class StrikeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Strike
        fields = ['epoch_ms', 'timestamp', 'latitude', 'longitude', 'strike_type']