from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

# --- TAMBAHKAN KODE DI BAWAH INI ---
@register.filter(name='has_group')
def has_group(user, group_name):
    """
    Penggunaan di template: {% if request.user|has_group:"koordinator" %}
    """
    if user.is_superuser:
        return True # Superuser selalu bisa akses
    return user.groups.filter(name=group_name).exists()