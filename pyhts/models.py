from __future__ import unicode_literals
from django.db import models
from django.conf import settings


class PlateFile(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL)
    upload_date = models.DateTimeField(auto_now_add=True)
    process_date = models.DateTimeField(null=True, blank=True)
    file = models.FileField()
