"""{% static %} + penanda versi, supaya operator tidak terjebak cache lama.

nginx menyajikan /static/ dengan `Cache-Control: public, immutable` dan masa
simpan 7 hari, sementara collectstatic di server produksi berjalan tanpa
ENVIRONMENT=production (DEBUG=True), sehingga nama berkas TIDAK diberi hash
(ManifestStaticFilesStorage tidak aktif). Akibatnya berkas dengan nama sama bisa
berubah isi sementara browser masih memakai salinan lama sampai 7 hari.

Tag ini menambahkan ?v=<mtime berkas>, jadi begitu isi berkas berubah URL-nya
ikut berubah dan browser langsung mengambil yang baru.
"""
import os

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def static_v(path):
    """Seperti {% static %}, tapi dengan ?v=<mtime>."""
    url = static(path)
    found = finders.find(path.lstrip('/'))
    try:
        version = int(os.path.getmtime(found)) if found else 0
    except OSError:
        version = 0
    if not version:
        return url
    separator = '&' if '?' in url else '?'
    return f'{url}{separator}v={version}'
