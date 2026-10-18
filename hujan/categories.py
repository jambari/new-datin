"""Kategori hujan baku (nilai di form) dan penyeragaman penulisan lama/impor.

Data arsip 2002–2018 memakai penulisan bebas ("Hujan Sangat Ringan", "Nihil",
"NIHIIL", "Hukan Ringan", ...). normalize_kategori() memetakannya ke nilai baku form.
"""
from .forms import KATEGORI_CHOICES

KATEGORI_KEYS = [key for key, _label in KATEGORI_CHOICES if key]
KATEGORI_LABELS = {
    "nihil": "Nihil", "sangat ringan": "Sangat Ringan", "ringan": "Ringan", "sedang": "Sedang",
    "lebat": "Lebat", "sangat lebat": "Sangat Lebat", "tak terukur": "Tak Terukur",
}
_TYPOS = {"hukan": "hujan", "huan": "hujan", "hujna": "hujan", "sanga t": "sangat", "nihiil": "nihil"}
_ALIASES = {"ttu": "tak terukur"}


def normalize_kategori(raw):
    """Nilai baku untuk teks kategori; '' bila kosong, None bila tidak dikenali."""
    text = " ".join((raw or "").lower().split())
    if not text:
        return ""
    for wrong, right in _TYPOS.items():
        text = text.replace(wrong, right)
    if text.startswith("hujan "):
        text = text[len("hujan "):]
    text = _ALIASES.get(text, text)
    return text if text in KATEGORI_KEYS else None


def kategori_label(raw):
    """Label tampilan ('Sangat Ringan') untuk teks kategori apa pun."""
    key = normalize_kategori(raw)
    if key is None:
        return "Lainnya"
    return KATEGORI_LABELS.get(key, "")
