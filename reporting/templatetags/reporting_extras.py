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
