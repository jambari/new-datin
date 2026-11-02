"""Sanitizer HTML sederhana untuk isi berita dari editor WYSIWYG.

Hanya tag/atribut yang aman yang dibiarkan. Script, iframe, form, dan
atribut event (onclick dsb.) dibuang supaya artikel tidak bisa dipakai
untuk menanam JavaScript di halaman publik.
"""
import re
from html import escape
from html.parser import HTMLParser

# Tag yang isinya ikut dibuang (bukan hanya tag-nya).
BLOCKED_TAGS = {
    'script', 'style', 'iframe', 'frame', 'frameset', 'object', 'embed',
    'applet', 'form', 'input', 'textarea', 'select', 'option', 'button',
    'link', 'meta', 'base', 'svg', 'math',
}

ALLOWED_TAGS = {
    'p', 'br', 'hr', 'div', 'span', 'strong', 'b', 'em', 'i', 'u', 's',
    'strike', 'sub', 'sup', 'blockquote', 'pre', 'code', 'h1', 'h2', 'h3',
    'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'a', 'img', 'figure', 'figcaption',
    'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td',
}

VOID_TAGS = {'br', 'hr', 'img'}

ALLOWED_ATTRS = {
    'href', 'title', 'target', 'rel', 'src', 'alt', 'width', 'height',
    'class', 'style', 'colspan', 'rowspan',
}

# Skema URL yang berbahaya.
_BAD_URL = re.compile(r'^\s*(javascript|vbscript|data\s*:\s*text/html)', re.I)
_SAFE_STYLE = re.compile(r'^\s*[a-z-]+\s*:', re.I)


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.parts = []
        self._skip_depth = 0

    # -- helper ---------------------------------------------------------
    def _clean_attrs(self, attrs):
        out = []
        for name, value in attrs:
            name = (name or '').lower()
            if name not in ALLOWED_ATTRS:
                continue
            if name.startswith('on'):
                continue
            value = value or ''
            if name in ('href', 'src') and _BAD_URL.search(value):
                continue
            if name == 'style' and not _SAFE_STYLE.match(value):
                continue
            out.append((name, value))
        return out

    # -- parser callbacks ----------------------------------------------
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in BLOCKED_TAGS:
            if tag not in VOID_TAGS:
                self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag not in ALLOWED_TAGS:
            return
        cleaned = self._clean_attrs(attrs)
        attr_text = ''.join(
            f' {name}="{escape(value, quote=True)}"' for name, value in cleaned
        )
        self.parts.append(f'<{tag}{attr_text}>')

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if tag in BLOCKED_TAGS or tag not in ALLOWED_TAGS:
            return
        cleaned = self._clean_attrs(attrs)
        attr_text = ''.join(
            f' {name}="{escape(value, quote=True)}"' for name, value in cleaned
        )
        self.parts.append(f'<{tag}{attr_text} />')

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in BLOCKED_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.parts.append(f'</{tag}>')

    def handle_data(self, data):
        if self._skip_depth:
            return
        self.parts.append(escape(data, quote=False))

    def handle_entityref(self, name):
        if self._skip_depth:
            return
        self.parts.append(f'&{name};')

    def handle_charref(self, name):
        if self._skip_depth:
            return
        self.parts.append(f'&#{name};')

    def result(self):
        return ''.join(self.parts)


def clean_html(html):
    """Kembalikan HTML yang sudah disaring."""
    if not html:
        return ''
    parser = _Sanitizer()
    parser.feed(html)
    parser.close()
    return parser.result()
