from django import template
import thunorweb
from django.core.serializers import serialize
from django.db.models.query import QuerySet
import json
from django.utils.safestring import mark_safe
from django.conf import settings

register = template.Library()


@register.filter
def jsonify(obj):
    if isinstance(obj, QuerySet):
        return serialize('json', obj)
    return mark_safe(json.dumps(obj))


@register.simple_tag
def sentry_environment():
    return settings.RAVEN_CONFIG['environment']


@register.simple_tag
def thunorweb_version():
    return thunorweb.__version__


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def startswith(text, starts):
    if isinstance(text, str):
        return text.startswith(starts)
    return False
