from __future__ import unicode_literals

from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_save
from django.db.utils import ProgrammingError


class ThunorConfig(AppConfig):
    name = 'thunorweb'

    def ready(self):
        # Set the site name now so we don't have to hit the DB on every view
        from django.contrib.sites.models import Site
        try:
            settings.SITE_NAME = Site.objects.get_current().name
        except ProgrammingError:
            # Exception generated if migrations haven't been run yet
            # Use default site name instead
            settings.SITE_NAME = 'Thunor'

        # Add a hook for new users to get added to a default group
        post_save.connect(add_to_default_group,
                          sender=settings.AUTH_USER_MODEL)


def add_to_default_group(sender, **kwargs):
    user = kwargs["instance"]
    if kwargs["created"]:
        from django.contrib.auth.models import Group
        group, _ = Group.objects.get_or_create(name='Public')
        user.groups.add(group)
