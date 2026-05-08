from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from repository.models import GempaMemusak
from repository.models import ShakemapEvent


class StaticViewSitemap(Sitemap):
    priority = 0.8
    changefreq = 'daily'
    protocol = 'http'

    def items(self):
        return [
            'landing',
            'gempa_public',
            'public_gempa_merusak',
            'public_shakemap_list',
            'public_petir',
            'public_magnetbumi',
            'public_about',
            'public_glosarium',
            'our_work',
            'public_ttm',
        ]

    def location(self, item):
        return reverse(item)


class ShakemapSitemap(Sitemap):
    priority = 0.6
    changefreq = 'monthly'
    protocol = 'http'

    def items(self):
        return ShakemapEvent.objects.order_by('-event_time')[:200]

    def location(self, obj):
        return reverse('public_shakemap_detail', args=[obj.pk])

    def lastmod(self, obj):
        return obj.event_time
