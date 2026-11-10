"""Peta isoseismal otomatis per kejadian gempa dirasakan.

Satu baris per hasil ShakeMap yang dikirim dari .50 (kunci = stempel waktu WIB 14 digit,
sama dengan ShakemapEvent). Peta hanya digambar bila ada laporan dirasakan.
"""
import datetime
import re

from django.db import models
from django.urls import reverse
from django.utils.text import slugify

HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = ["", "januari", "februari", "maret", "april", "mei", "juni", "juli", "agustus", "september",
         "oktober", "november", "desember"]


_ARAH = {'utara', 'selatan', 'timur', 'barat', 'laut', 'daya', 'tenggara', 'timurlaut', 'baratlaut',
         'baratdaya', 'tenggara', 'timurtenggara'}
_PROVINSI = re.compile(r'^(PAPUA|MALUKU)\w*$', re.I)          # PAPUA, PAPUABRT, PAPUAPGNGN, MALUKU, …


class IsoseismalQuerySet(models.QuerySet):
    def public(self):
        """Peta yang sudah tergambar, ada laporan dirasakan, dan tidak disembunyikan staf."""
        return self.filter(is_hidden=False).exclude(image="").exclude(image__isnull=True)


class IsoseismalMap(models.Model):
    wib_id = models.CharField('ID ShakeMap (WIB)', max_length=14, unique=True,
                              help_text='Stempel waktu WIB 14 digit, sama dengan ShakemapEvent.')
    slug = models.SlugField(max_length=160, unique=True)
    event_time = models.DateTimeField('waktu gempa (UTC)', db_index=True)
    latitude = models.FloatField('lintang')
    longitude = models.FloatField('bujur')
    magnitude = models.FloatField('magnitudo')
    depth = models.FloatField('kedalaman (km)')
    lokasi = models.CharField(max_length=255, blank=True)

    grid = models.FileField('grid MMI ShakeMap (.npz)', upload_to='isoseismal/grid/', blank=True)
    shakemap_dir = models.CharField('run ShakeMap di .50', max_length=120, blank=True,
                                    help_text='Folder di data_MMI yang dipakai, mis. <WIB>_37_-2320_140500_<WIB>_composite.')
    shakemap_mtime = models.FloatField('waktu ubah grid.xml di .50', null=True, blank=True)
    stations = models.JSONField('stasiun akselerograf', default=list, blank=True)
    observed = models.JSONField('intensitas teramati ShakeMap', default=list, blank=True)
    felt = models.JSONField('titik dirasakan', default=list, blank=True)
    felt_text = models.TextField('teks laporan dirasakan', blank=True)
    felt_sources = models.JSONField('sumber laporan dirasakan', default=list, blank=True)
    wilayah = models.JSONField('MMI per kabupaten/kota', default=list, blank=True)

    image = models.ImageField('peta', upload_to='isoseismal/', blank=True)
    generated_at = models.DateTimeField('digambar', null=True, blank=True)
    is_hidden = models.BooleanField('sembunyikan dari publik', default=False)
    note = models.CharField('catatan proses', max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = IsoseismalQuerySet.as_manager()

    class Meta:
        ordering = ['-event_time']
        verbose_name = 'Peta Isoseismal'
        verbose_name_plural = 'Peta Isoseismal'

    def __str__(self):
        return f'{self.wib_id} M{self.magnitude:.1f} {self.lokasi}'

    # ── Waktu & teks ──────────────────────────────────────────────────────────
    @property
    def wit_time(self):
        return self.event_time.astimezone(datetime.timezone(datetime.timedelta(hours=9)))

    @property
    def wilayah_singkat(self):
        """Nama wilayah dari lokasi ShakeMap, mis. '31 km TimurLaut KAB-JAYAPURA-PAPUA' → 'Kab. Jayapura',
        '35 km BaratDaya LANNYJAYA-PAPUAPEGNGN' → 'Lannyjaya', '64 km Barat Daya KAIMANA-PAPUABRT' → 'Kaimana'."""
        words = (self.lokasi or '').replace('-', ' ').split()
        if len(words) >= 2 and words[1].lower() == 'km':
            words = words[2:]
        while words and words[0].lower() in _ARAH:
            words = words[1:]
        while words and _PROVINSI.match(words[-1]):
            words = words[:-1]
        text = ' '.join(words).title().replace('Kab ', 'Kab. ')
        return text or 'Papua'

    @property
    def title(self):
        return f'Peta Isoseismal Gempabumi {self.wilayah_singkat}, {self.tanggal}'

    @property
    def tanggal_panjang(self):
        """Mis. 'Jumat, 22 Mei 2026' (WIT)."""
        return f'{HARI[self.wit_time.weekday()]}, {self.tanggal}'

    @property
    def tanggal(self):
        """Mis. '22 Mei 2026' (WIT)."""
        t = self.wit_time
        return f'{t.day} {BULAN[t.month].title()} {t.year}'

    @property
    def koordinat(self):
        ns = 'LU' if self.latitude >= 0 else 'LS'
        return f'{abs(self.latitude):.2f} {ns} – {abs(self.longitude):.2f} BT'

    @property
    def mmi_max(self):
        values = [f['mmi'] for f in self.felt] + [s['mmi'] for s in self.stations if s.get('mmi') is not None]
        return max(values) if values else None

    def build_slug(self):
        t = self.wit_time
        base = slugify(f'peta isoseismal gempabumi {self.wilayah_singkat} {t.day} {BULAN[t.month]} {t.year}')[:140]
        slug, n = base, 2
        while IsoseismalMap.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f'{base}-{n}'
            n += 1
        return slug

    def get_absolute_url(self):
        return reverse('isoseismal:detail', args=[self.slug])
