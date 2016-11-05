from django import template
import pyhts.helpers
from django.core.serializers import serialize
from django.db.models.query import QuerySet
import json
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def formatdose(value):
    if value == '':
        return ''

    return pyhts.helpers.format_dose(value)


@register.filter
def jsonify(object):
    if isinstance(object, QuerySet):
        return serialize('json', object)
    return mark_safe(json.dumps(object))
