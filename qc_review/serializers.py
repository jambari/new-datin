from rest_framework import serializers
from .models import Event, StationResult


class StationResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = StationResult
        fields = "__all__"


class EventSerializer(serializers.ModelSerializer):
    station_results = StationResultSerializer(many=True, read_only=True)
    qc_summary = serializers.ReadOnlyField()

    class Meta:
        model = Event
        fields = "__all__"
