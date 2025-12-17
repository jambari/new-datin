from rest_framework import serializers
from .models import EarthquakeEvent

class EarthquakeEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = EarthquakeEvent
        fields = '__all__'