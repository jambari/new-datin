from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Ambil nilai dari dict secara dinamis di template."""
    if mapping is None:
        return None
    return mapping.get(key)
