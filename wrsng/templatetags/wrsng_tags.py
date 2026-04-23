from django import template
from wrsng.constants import CODE_TO_STATION

register = template.Library()

@register.filter
def station_display(wrs_code):
    return CODE_TO_STATION.get(wrs_code, wrs_code)
