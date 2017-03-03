from __future__ import unicode_literals

from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_save


class PyhtsConfig(AppConfig):
    name = 'pyhts'

    def ready(self):
        post_save.connect(add_to_default_group,
                          sender=settings.AUTH_USER_MODEL)


def add_to_default_group(sender, **kwargs):
    user = kwargs["instance"]
    if kwargs["created"]:
        from django.contrib.auth.models import Group
        group, _ = Group.objects.get_or_create(name='Public')
        user.groups.add(group)
