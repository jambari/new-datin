from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from repository.models import Bulletin, FeltEarthquake, GempaMemusak, SiaranPress
from berita.models import Berita
from isoseismal.models import IsoseismalMap


class _Base(Sitemap):
    protocol = 'https'


class StaticViewSitemap(_Base):
    changefreq = 'daily'

    # (nama URL, prioritas)
    PAGES = [
        ('landing', 1.0),
        ('gempa_public', 0.9),
        ('isoseismal:list', 0.9),
        ('public_shakemap_list', 0.8),
        ('berita:list', 0.8),
        ('public_gempa_merusak', 0.8),
        ('isoseismal:scenario_list', 0.7),
        ('public_spectra_list', 0.6),
        ('public_skala_mmi', 0.6),
        ('public_petir', 0.6),
        ('public_magnetbumi', 0.6),
        ('public_magnetbumi_indices', 0.5),
        ('public_siaranpress_list', 0.6),
        ('public_bulletin_list', 0.5),
        ('public_ttm', 0.5),
        ('public_about', 0.7),
        ('public_glosarium', 0.5),
        ('our_work', 0.5),
    ]

    def items(self):
        return [name for name, _ in self.PAGES]

    def location(self, item):
        return reverse(item)

    def priority(self, item):
        return dict(self.PAGES)[item]


class IsoseismalSitemap(_Base):
    priority = 0.8
    changefreq = 'monthly'

    def items(self):
        return list(IsoseismalMap.objects.public()) + list(IsoseismalMap.objects.public_scenarios())

    def location(self, obj):
        return obj.get_absolute_url()

    def lastmod(self, obj):
        return obj.updated_at


class GempaMerusakSitemap(_Base):
    priority = 0.5
    changefreq = 'yearly'

    def items(self):
        return GempaMemusak.objects.order_by('-no')

    def location(self, obj):
        return reverse('public_gempa_merusak_detail', args=[obj.pk])


class ShakemapSitemap(_Base):
    """Halaman /shakemap/<pk>/ memakai pk FeltEarthquake (bukan ShakemapEvent)."""
    priority = 0.6
    changefreq = 'monthly'

    def items(self):
        return FeltEarthquake.objects.order_by('-event_datetime')[:500]

    def location(self, obj):
        return reverse('public_shakemap_detail', args=[obj.pk])

    def lastmod(self, obj):
        return obj.fetched_at


class BeritaSitemap(_Base):
    priority = 0.7
    changefreq = 'weekly'

    def items(self):
        return Berita.objects.published().order_by('-published_at')

    def location(self, obj):
        return obj.get_absolute_url()

    def lastmod(self, obj):
        return obj.updated_at


class SiaranPressSitemap(_Base):
    priority = 0.6
    changefreq = 'monthly'

    def items(self):
        return SiaranPress.objects.order_by('-created_at')[:500]

    def location(self, obj):
        return reverse('public_siaranpress_detail', args=[obj.pk])

    def lastmod(self, obj):
        return obj.updated_at


class BulletinSitemap(_Base):
    priority = 0.4
    changefreq = 'yearly'

    def items(self):
        return Bulletin.objects.order_by('-created_at')

    def location(self, obj):
        return reverse('public_bulletin_detail', args=[obj.pk])

    def lastmod(self, obj):
        return obj.updated_at
