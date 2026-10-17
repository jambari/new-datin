"""Pembatasan akses logbook ke jaringan kantor.

IP pengunjung diambil dari CF-Connecting-IP hanya bila permintaan benar-benar datang
dari server Cloudflare (alamat lawan bicara nginx, diteruskan sebagai X-Real-IP).
Header X-Forwarded-For tidak dipakai karena bisa diisi sendiri oleh pengunjung.
"""
import ipaddress
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# Rentang IP Cloudflare (https://www.cloudflare.com/ips/).
CLOUDFLARE_NETWORKS = [ipaddress.ip_network(n) for n in (
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18",
    "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17",
    "162.158.0.0/15", "104.16.0.0/13", "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
    "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32", "2405:8100::/32",
    "2a06:98c0::/29", "2c0f:f248::/32",
)]

DEFAULT_OFFICE_NETWORKS = ("36.91.166.184/29", "127.0.0.1/32", "::1/128")


def _parse_ip(value):
    try:
        return ipaddress.ip_address((value or "").strip())
    except ValueError:
        return None


def _in(ip, networks):
    return ip is not None and any(ip.version == n.version and ip in n for n in networks)


def client_ip(request):
    """IP asli pengunjung (objek ipaddress) atau None."""
    peer = _parse_ip(request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR"))
    if _in(peer, CLOUDFLARE_NETWORKS):
        return _parse_ip(request.META.get("HTTP_CF_CONNECTING_IP")) or peer
    return peer


def office_networks():
    nets = []
    for item in getattr(settings, "LOGBOOK_ALLOWED_NETWORKS", None) or DEFAULT_OFFICE_NETWORKS:
        try:
            nets.append(ipaddress.ip_network(item.strip(), strict=False))
        except ValueError:
            logger.warning("LOGBOOK_ALLOWED_NETWORKS: entri tidak valid diabaikan: %r", item)
    return nets


def is_office_request(request):
    """(diizinkan?, ip sebagai teks). Penolakan dicatat agar IP baru kantor mudah ditambahkan."""
    ip = client_ip(request)
    allowed = _in(ip, office_networks())
    if not allowed:
        logger.warning("Logbook: akses ditolak dari IP %s (path %s)", ip, request.path)
    return allowed, str(ip) if ip else "tidak diketahui"
