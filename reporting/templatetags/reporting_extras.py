from django import template

from reporting.common import fmt

register = template.Library()


@register.filter
def idn(value, digits=2):
    """Format angka Indonesia: {{ v|idn:4 }}."""
    try:
        return fmt(value, int(digits))
    except (TypeError, ValueError):
        return value


@register.filter
def get_item(mapping, key):
    return mapping.get(key) if mapping else None


@register.filter
def pairs(rows):
    """Bagi daftar menjadi dua kolom berdampingan: [(r1, r17), (r2, r18), ...]."""
    rows = list(rows)
    half = (len(rows) + 1) // 2
    left, right = rows[:half], rows[half:]
    return [(left[i], right[i] if i < len(right) else None) for i in range(half)]
