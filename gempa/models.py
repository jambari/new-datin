from django.db import models
import reversion
import math
from datetime import datetime


def cardinal_direction(lat_eq, lon_eq, lat_city, lon_city):
    dlat = lat_eq - lat_city
    dlon = lon_eq - lon_city
    if dlat < 0 and dlon < 0:
        return 'BaratDaya'
    if dlat > 0 and dlon < 0:
        return 'BaratLaut'
    if dlat > 0 and dlon > 0:
        return 'TimurLaut'
    if dlat < 0 and dlon > 0:
        return 'Tenggara'
    if dlat > 0:
        return 'Utara'
    if dlat < 0:
        return 'Selatan'
    if dlon < 0:
        return 'Barat'
    return 'Timur'


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6367
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def nearest_city_description(lintang, bujur):
    try:
        lat = float(lintang)
        lon = float(bujur)
        cities = list(City.objects.all())
        if not cities:
            return '-'
        nearest = min(cities, key=lambda c: haversine_km(lat, lon, float(c.latitude), float(c.longitude)))
        dist = round(haversine_km(lat, lon, float(nearest.latitude), float(nearest.longitude)))
        arah = cardinal_direction(lat, lon, float(nearest.latitude), float(nearest.longitude))
        return f"{dist} km {arah} {nearest.name}"
    except Exception:
        return '-'


def compute_delta(tanggal, origin, created_at):
    try:
        origin_dt = datetime.strptime(f"{tanggal} {str(origin)[:8]}", "%Y-%m-%d %H:%M:%S")
        if isinstance(created_at, datetime):
            created_dt = created_at.replace(tzinfo=None)
        else:
            created_dt = datetime.strptime(str(created_at)[:19], "%Y-%m-%d %H:%M:%S")
        diff = created_dt - origin_dt
        total_minutes = diff.total_seconds() / 60
        total_seconds = abs(int(diff.total_seconds()))
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        label = "ONTIME" if abs(total_minutes) <= 10 else "LATE"
        return f"{h:02d}:{m:02d}:{s:02d} {label}"
    except Exception:
        return '-'


class City(models.Model):
    name = models.CharField(max_length=191)
    latitude = models.DecimalField(max_digits=10, decimal_places=6)
    longitude = models.DecimalField(max_digits=10, decimal_places=6)

    class Meta:
        db_table = 'katalog_cities'
        managed = True
        verbose_name = 'Kota'
        verbose_name_plural = 'Kota'

    def __str__(self):
        return self.name


@reversion.register()
class Gempa(models.Model):
    SUMBER_CHOICES = [
        ('angkasa', 'Angkasa'), ('pgr v', 'PGR V'), ('pgn', 'PGN'),
        ('bmkg', 'BMKG'), ('usgs', 'USGS'),
    ]
    TYPE_CHOICES = [('M', 'M'), ('MLv', 'MLv'), ('Mw', 'Mw'), ('Mwp', 'Mwp')]
    PETUGAS_CHOICES = [
        ('alif', 'Alif'), ('berlian', 'Berlian'), ('canggih', 'Canggih'),
        ('danang', 'Danang'), ('gogo', 'Gogo'), ('jambari', 'Jambari'),
        ('lidya', 'Lidya'), ('netty', 'Netty'), ('prasetia', 'Prasetia'),
        ('purnama', 'Purnama'), ('rosi', 'Rosi'), ('rivaldo', 'Rivaldo'),
        ('syawal', 'Syawal'), ('umum', 'Umum'),
    ]

    event_id = models.CharField(max_length=64, unique=True, null=True, blank=True)

    tanggal = models.DateField()
    origin = models.CharField(max_length=191)
    lintang = models.CharField(max_length=191)
    bujur = models.DecimalField(max_digits=5, decimal_places=2)
    magnitudo = models.DecimalField(max_digits=2, decimal_places=1)
    type = models.CharField(max_length=191, choices=TYPE_CHOICES, default='M', blank=True, null=True)
    depth = models.IntegerField()
    ket = models.CharField(max_length=191, blank=True, default='')
    terasa = models.BooleanField(default=False)
    terdampak = models.CharField(max_length=191, blank=True, null=True)
    narasi = models.TextField(blank=True, null=True)
    sumber = models.CharField(max_length=191, choices=SUMBER_CHOICES, default='angkasa', blank=True, null=True)
    petugas = models.CharField(max_length=191, choices=PETUGAS_CHOICES, default='umum', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)
    delta = models.CharField(max_length=191, blank=True, null=True)

    class Meta:
        db_table = 'katalog_gempas'
        managed = True
        ordering = ['-tanggal', '-origin']
        verbose_name = 'Gempa JAY'
        verbose_name_plural = 'Gempa JAY'

    def __str__(self):
        return f"{self.tanggal} {self.origin} M{self.magnitudo}"

    @property
    def wit(self):
        try:
            dt = datetime.strptime(f"{self.tanggal} {str(self.origin)[:8]}", "%Y-%m-%d %H:%M:%S")
            from datetime import timedelta
            return (dt + timedelta(hours=9)).strftime("%H:%M:%S")
        except Exception:
            return '-'

    @property
    def lat_display(self):
        return _format_lat(str(self.lintang))

    @property
    def lon_display(self):
        return f"{self.bujur} BT"


@reversion.register()
class Balaigempa(models.Model):
    TYPE_CHOICES = [('M', 'M'), ('MLv', 'MLv'), ('Mw', 'Mw'), ('Mwp', 'Mwp')]

    event_id = models.CharField(max_length=64, unique=True, null=True, blank=True)

    tanggal = models.DateField()
    origin = models.CharField(max_length=191)
    lintang = models.CharField(max_length=191)
    bujur = models.DecimalField(max_digits=8, decimal_places=5)
    magnitudo = models.DecimalField(max_digits=2, decimal_places=1)
    type = models.CharField(max_length=191, choices=TYPE_CHOICES, default='M', blank=True, null=True)
    depth = models.IntegerField()
    ket = models.CharField(max_length=191, blank=True, null=True)
    terasa = models.BooleanField(default=False)
    terdampak = models.CharField(max_length=191, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)
    delta = models.CharField(max_length=191, blank=True, null=True)

    class Meta:
        db_table = 'katalog_balaigempas'
        managed = True
        ordering = ['-tanggal', '-origin']
        verbose_name = 'Gempa PGR V (Balai)'
        verbose_name_plural = 'Gempa PGR V (Balai)'

    def __str__(self):
        return f"{self.tanggal} {self.origin} M{self.magnitudo}"

    @property
    def wit(self):
        try:
            dt = datetime.strptime(f"{self.tanggal} {str(self.origin)[:8]}", "%Y-%m-%d %H:%M:%S")
            from datetime import timedelta
            return (dt + timedelta(hours=9)).strftime("%H:%M:%S")
        except Exception:
            return '-'


@reversion.register()
class Gempasorong(models.Model):
    TYPE_CHOICES = [('M', 'M'), ('MLv', 'MLv'), ('Mw', 'Mw'), ('Mwp', 'Mwp')]

    event_id = models.CharField(max_length=64, unique=True, null=True, blank=True)

    tanggal = models.DateField()
    origin = models.CharField(max_length=191)
    lintang = models.CharField(max_length=191)
    bujur = models.CharField(max_length=191)
    magnitudo = models.DecimalField(max_digits=2, decimal_places=1)
    type = models.CharField(max_length=191, choices=TYPE_CHOICES, default='M', blank=True, null=True)
    depth = models.IntegerField()
    ket = models.CharField(max_length=191, blank=True, null=True)
    terasa = models.BooleanField(default=False)
    terdampak = models.CharField(max_length=191, blank=True, null=True)
    delta = models.CharField(max_length=191, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        db_table = 'katalog_gempasorongs'
        managed = True
        ordering = ['-tanggal', '-origin']
        verbose_name = 'Gempa Sorong (SWI)'
        verbose_name_plural = 'Gempa Sorong (SWI)'

    def __str__(self):
        return f"{self.tanggal} {self.origin} M{self.magnitudo}"


@reversion.register()
class Gempanabire(models.Model):
    TYPE_CHOICES = [('M', 'M'), ('MLv', 'MLv'), ('Mw', 'Mw'), ('Mwp', 'Mwp')]

    event_id = models.CharField(max_length=64, unique=True, null=True, blank=True)

    tanggal = models.DateField()
    origin = models.CharField(max_length=191)
    lintang = models.CharField(max_length=191)
    bujur = models.CharField(max_length=191)
    magnitudo = models.DecimalField(max_digits=2, decimal_places=1)
    type = models.CharField(max_length=191, choices=TYPE_CHOICES, default='M', blank=True, null=True)
    depth = models.IntegerField()
    ket = models.CharField(max_length=191, blank=True, null=True)
    terasa = models.BooleanField(default=False)
    terdampak = models.CharField(max_length=191, blank=True, null=True)
    delta = models.CharField(max_length=191, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        db_table = 'katalog_gempanabires'
        managed = True
        ordering = ['-tanggal', '-origin']
        verbose_name = 'Gempa Nabire (NBPI)'
        verbose_name_plural = 'Gempa Nabire (NBPI)'

    def __str__(self):
        return f"{self.tanggal} {self.origin} M{self.magnitudo}"


@reversion.register()
class Satudatagempa(models.Model):
    SUMBER_CHOICES = [
        ('BMKG-JAY', 'BMKG JAY'), ('BMKG-PGR V', 'BMKG PGR V'),
        ('BMKG-SWI', 'BMKG SWI'), ('BMKG-NBPI', 'BMKG NBPI'),
        ('BMKG-NGJ', 'BMKG Nganjuk'), ('BMKG', 'BMKG'),
    ]

    event_id = models.CharField(max_length=64, unique=True, null=True, blank=True)

    tanggal = models.DateField()
    origin = models.CharField(max_length=191)
    lintang = models.CharField(max_length=191)
    bujur = models.CharField(max_length=191)
    magnitudo = models.DecimalField(max_digits=2, decimal_places=1)
    depth = models.IntegerField()
    ket = models.CharField(max_length=191, blank=True, null=True)
    sumber = models.CharField(max_length=191, choices=SUMBER_CHOICES, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        db_table = 'katalog_satudatagempas'
        managed = True
        ordering = ['-tanggal', '-origin']
        verbose_name = 'Satu Data Gempa'
        verbose_name_plural = 'Satu Data Gempa'

    def __str__(self):
        return f"{self.tanggal} {self.origin} M{self.magnitudo} ({self.sumber})"


@reversion.register()
class Gempanganjuk(models.Model):
    TYPE_CHOICES = [('M', 'M'), ('MLv', 'MLv'), ('Mw', 'Mw'), ('Mwp', 'Mwp')]

    event_id = models.CharField(max_length=64, unique=True, null=True, blank=True)

    tanggal = models.DateField()
    origin = models.CharField(max_length=191)
    lintang = models.CharField(max_length=191)
    bujur = models.CharField(max_length=191)
    magnitudo = models.DecimalField(max_digits=2, decimal_places=1)
    type = models.CharField(max_length=191, choices=TYPE_CHOICES, default='M', blank=True, null=True)
    depth = models.IntegerField()
    ket = models.CharField(max_length=191, blank=True, null=True)
    terasa = models.BooleanField(default=False)
    terdampak = models.CharField(max_length=191, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        db_table = 'katalog_gempanganjuks'
        managed = True
        ordering = ['-tanggal', '-origin']
        verbose_name = 'Gempa Nganjuk (NGJ)'
        verbose_name_plural = 'Gempa Nganjuk (NGJ)'

    def __str__(self):
        return f"{self.tanggal} {self.origin} M{self.magnitudo}"


@reversion.register()
class Significant(models.Model):
    event_id = models.CharField(max_length=64, unique=True, null=True, blank=True)

    tanggal = models.CharField(max_length=191)
    jam = models.CharField(max_length=191)
    lintang = models.CharField(max_length=191)
    bujur = models.CharField(max_length=191)
    magnitudo = models.CharField(max_length=191)
    depth = models.IntegerField()
    lokasi = models.CharField(max_length=191, blank=True, null=True)
    dirasakan = models.CharField(max_length=191, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        db_table = 'katalog_significants'
        managed = True
        ordering = ['-created_at']
        verbose_name = 'Gempa Signifikan'
        verbose_name_plural = 'Gempa Signifikan'

    def __str__(self):
        return f"{self.tanggal} {self.jam} M{self.magnitudo}"


def _format_lat(lat_str):
    try:
        val = float(lat_str)
        if val < 0:
            return f"{abs(val):.2f} LS"
        return f"{val:.2f} LU"
    except Exception:
        return lat_str


class FocalMechanism(models.Model):
    """Focal mechanism (strike, dip, rake) untuk gempa utama.

    source + event_pk menunjuk ke event pada model sumber
    (Gempa/Balaigempa/Gempasorong/Gempanabire).
    is_auto=True berarti diambil otomatis dari USGS FDSN.
    """
    source = models.CharField(max_length=16)
    event_pk = models.PositiveIntegerField()
    strike = models.FloatField()
    dip = models.FloatField()
    rake = models.FloatField()
    magnitude = models.FloatField(null=True, blank=True)
    depth = models.FloatField(null=True, blank=True)
    offset_lat = models.FloatField(null=True, blank=True)
    offset_lon = models.FloatField(null=True, blank=True)
    is_auto = models.BooleanField(default=False)
    origin_label = models.CharField(max_length=191, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'katalog_focal_mechanisms'
        unique_together = ('source', 'event_pk')
        verbose_name = 'Focal Mechanism'
        verbose_name_plural = 'Focal Mechanisms'

    def __str__(self):
        return f"{self.source}#{self.event_pk} {self.strike}/{self.dip}/{self.rake}"
