from django import template
from django.template.defaultfilters import stringfilter
import pyhts.helpers

register = template.Library()


@register.filter
def formatdose(value):
    if value == '':
        return ''

    return pyhts.helpers.format_dose(value)
