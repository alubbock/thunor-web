# -*- coding: utf-8 -*-
# Generated by Django 1.10.3 on 2016-11-19 18:50
from __future__ import unicode_literals

from django.db import migrations
from django.conf import settings


def insert_sites(apps, schema_editor):
    """Populate the sites model"""
    Site = apps.get_model('sites', 'Site')
    Site.objects.all().delete()

    # Register SITE_ID = 1
    Site.objects.create(pk=1, domain=settings.HOSTNAME, name='Thunor')


class Migration(migrations.Migration):

    dependencies = [
        ('sites', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(insert_sites)
    ]
