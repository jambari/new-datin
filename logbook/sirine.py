"""Cek status sirene tsunami lewat panel Alfar Smart (sirine.id:8088).

Latar belakang: operator perlu tahu sirene hidup atau mati TANPA membunyikannya.
Tombol di panel itu ada tiga (semuanya GET ke /activate/<device>/<aksi>):

    real  -> membunyikan sirene tsunami SESUNGGUHNYA (alarm palsu!)
    test  -> membunyikan sirene untuk uji
    ping  -> hanya mengecek jaringan (ICMP), TIDAK membunyikan apa pun

Modul ini HANYA boleh memanggil `ping`. Penjagaannya berlapis:

1. `build_action_url()` menolak aksi apa pun selain 'ping' — jadi tidak ada cara
   membentuk URL 'real'/'test' dari kode ini.
2. `_guard()` memeriksa setiap request: path yang mengandung real/test/play/
   start/stop/trigger/bunyi/alarm langsung ditolak, POST hanya boleh ke login,
   dan GET ke /activate/... hanya boleh yang berakhiran /ping.
3. Ada tes yang memastikan dua penjagaan di atas benar-benar menolak (lihat
   logbook/tests.py::SirineSafetyTest) supaya refactor tidak menghapusnya diam-diam.

Kredensial diambil dari settings (SIRINE_USER / SIRINE_PASS, dari .env).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests

#: Satu-satunya aksi yang boleh dipanggil modul ini.
ALLOWED_ACTION = 'ping'

#: Aksi berbahaya di panel vendor — tidak akan pernah dipanggil.
FORBIDDEN_ACTIONS = ('real', 'test', 'play', 'start', 'stop',
                     'trigger', 'bunyi', 'alarm', 'activate')

#: Penjaga path: cocokkan segmen aksi yang berbahaya.
FORBIDDEN_PATH_RE = re.compile(
    r'/(real|test|play|start|stop|trigger|bunyi|alarm)(/|$)', re.IGNORECASE
)

#: Baris hasil ping: "4 packets transmitted, 4 received, 0% packet loss, time 3006ms"
PING_LINE_RE = re.compile(
    r'(\d+)\s+packets?\s+transmitted,\s*(\d+)\s+received,\s*(\d+)%\s*packet\s+loss',
    re.IGNORECASE,
)


class SirineError(Exception):
    """Kesalahan umum modul sirene."""


class SirineSafetyError(SirineError):
    """Ditolak oleh pengaman: percobaan memanggil aksi selain ping."""


class SirineAuthError(SirineError):
    """Login ke panel sirene gagal / sesi tidak berlaku."""


class SirineCheckError(SirineError):
    """Ping terkirim tapi hasilnya tidak bisa dibaca."""


@dataclass
class PingResult:
    """Hasil satu kali ping."""

    transmitted: int
    received: int
    loss_percent: int
    status: str            # 'ON' atau 'OFF'
    message: str           # pesan mentah dari panel

    @property
    def is_on(self) -> bool:
        return self.status == 'ON'

    def as_dict(self) -> dict:
        return {
            'status':        self.status,
            'transmitted':   self.transmitted,
            'received':      self.received,
            'loss_percent':  self.loss_percent,
            'message':       self.message,
        }


def build_action_url(base_url: str, device_id: str, action: str = ALLOWED_ACTION) -> str:
    """Bentuk URL aksi panel — menolak apa pun selain 'ping'.

    Ini pengaman utama: kode lain tidak bisa "salah tulis" menjadi aksi real.
    """
    action = (action or '').strip().lower()
    if action in FORBIDDEN_ACTIONS:
        raise SirineSafetyError(
            f'Aksi {action!r} DILARANG — itu membunyikan sirene. Hanya {ALLOWED_ACTION!r} yang diizinkan.'
        )
    if action != ALLOWED_ACTION:
        raise SirineSafetyError(
            f'Hanya aksi {ALLOWED_ACTION!r} yang diizinkan, bukan {action!r}.'
        )
    url = f"{base_url.rstrip('/')}/activate/{device_id}/{ALLOWED_ACTION}"
    # sabuk pengaman terakhir
    if not urlparse(url).path.endswith(f'/{ALLOWED_ACTION}'):
        raise SirineSafetyError(f'URL tidak berakhir /{ALLOWED_ACTION}: {url}')
    return url


def parse_ping_message(message: str) -> PingResult:
    """Ubah pesan panel menjadi PingResult.

    Aturan operator: 4 transmitted & 4 received & 0% loss -> ON, selain itu OFF.
    """
    text = (message or '').strip()
    match = PING_LINE_RE.search(text)
    if not match:
        raise SirineCheckError(f'Format hasil ping tidak dikenali: {text!r}')

    transmitted, received, loss = (int(g) for g in match.groups())
    is_on = transmitted > 0 and received == transmitted and loss == 0
    return PingResult(
        transmitted=transmitted,
        received=received,
        loss_percent=loss,
        status='ON' if is_on else 'OFF',
        message=text,
    )


class SirineClient:
    """Klien panel sirene: login lalu ping. Tidak ada aksi lain."""

    def __init__(self, base_url: str, username: str, password: str,
                 device_id: str, timeout: int = 30, session=None):
        if not (base_url and username and password and device_id):
            raise SirineError(
                'Konfigurasi sirene belum lengkap (SIRINE_BASE_URL/USER/PASS/DEVICE_ID).'
            )
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.device_id = device_id
        self.timeout = timeout
        self.login_url = urljoin(self.base_url + '/', 'login/')
        self.ping_url = build_action_url(self.base_url, device_id)
        self.session = session or requests.Session()
        self.session.headers.update({'User-Agent': 'datin-logbook-sirine-check/1.0'})
        self._logged_in = False

    # ── pengaman ─────────────────────────────────────────────────────────────

    def _guard(self, method: str, url: str) -> None:
        """Tolak setiap request yang bisa membunyikan sirene."""
        path = urlparse(url).path
        if FORBIDDEN_PATH_RE.search(path):
            raise SirineSafetyError(
                f'DITOLAK: {path!r} adalah aksi membunyikan sirene.'
            )
        if method.upper() == 'POST' and path != '/login/':
            raise SirineSafetyError(
                f'DITOLAK: hanya login yang boleh POST, bukan {path!r}.'
            )
        if method.upper() == 'GET' and path.startswith('/activate/'):
            if not path.endswith(f'/{ALLOWED_ACTION}'):
                raise SirineSafetyError(
                    f'DITOLAK: GET ke {path!r} bukan aksi {ALLOWED_ACTION!r}.'
                )

    def _request(self, method: str, url: str, **kwargs):
        self._guard(method, url)
        kwargs.setdefault('timeout', self.timeout)
        try:
            return self.session.request(method, url, **kwargs)
        except requests.RequestException as exc:
            raise SirineError(f'Gagal menghubungi panel sirene: {exc}') from exc

    # ── alur ─────────────────────────────────────────────────────────────────

    def login(self) -> None:
        """GET halaman login (ambil CSRF) lalu POST kredensial."""
        page = self._request('GET', self.login_url, allow_redirects=True)
        if page.status_code != 200:
            raise SirineAuthError(f'Halaman login membalas HTTP {page.status_code}')

        token = self._extract_csrf(page.text)
        if not token:
            raise SirineAuthError('csrfmiddlewaretoken tidak ditemukan di halaman login')

        resp = self._request(
            'POST', self.login_url,
            data={
                'csrfmiddlewaretoken': token,
                'username': self.username,
                'password': self.password,
                'next': '/',
            },
            headers={'Referer': self.login_url},
            allow_redirects=False,
        )
        # Login sukses -> 302 ke '/', gagal -> 200 (formulir diulang)
        if resp.status_code != 302:
            raise SirineAuthError(
                'Login sirene gagal (username/password ditolak panel).'
            )
        self._logged_in = True

    def ping(self) -> PingResult:
        """Panggil aksi ping (satu-satunya aksi yang diizinkan) dan baca hasilnya."""
        if not self._logged_in:
            self.login()

        resp = self._request('GET', self.ping_url,
                             headers={'Accept': 'application/json',
                                      'X-Requested-With': 'XMLHttpRequest'})
        if resp.status_code in (301, 302):
            raise SirineAuthError('Sesi sirene berakhir — panel meminta login lagi.')
        if resp.status_code != 200:
            raise SirineCheckError(f'Ping membalas HTTP {resp.status_code}')

        try:
            payload = resp.json()
        except ValueError as exc:
            raise SirineCheckError('Balasan ping bukan JSON.') from exc

        message = ((payload or {}).get('data') or {}).get('message')
        if not message:
            raise SirineCheckError(f'Balasan ping tanpa data.message: {payload!r}')
        return parse_ping_message(message)

    @staticmethod
    def _extract_csrf(html: str) -> str:
        match = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', html or '')
        if match:
            return match.group(1)
        match = re.search(r'name=csrfmiddlewaretoken\s+value="([^"]+)"', html or '')
        return match.group(1) if match else ''
