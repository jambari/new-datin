from django.db import models

# Create your models here.
class SunMoonEvent(models.Model):
    date = models.DateField()
    city = models.CharField(max_length=100)
    sun_rise = models.DateTimeField(null=True, blank=True)
    sun_set = models.DateTimeField(null=True, blank=True)
    moon_rise = models.DateTimeField(null=True, blank=True)
    moon_set = models.DateTimeField(null=True, blank=True)
    moon_phase = models.FloatField(null=True, blank=True)  # 0=new, 0.5=full, 1=new

    class Meta:
        unique_together = ('date', 'city')
        ordering = ['date']

    def __str__(self):
        return f"{self.city} {self.date}"
