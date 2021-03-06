# -*- coding: utf-8 -*-
# Generated by Django 1.11.10 on 2018-04-19 22:35
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('thunorweb', '0009_tags_createm2m'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='celllinetag',
            unique_together=set([('owner', 'tag_category', 'tag_name')]),
        ),
        migrations.RemoveField(
            model_name='celllinetag',
            name='cell_line',
        ),
        migrations.AlterUniqueTogether(
            name='drugtag',
            unique_together=set([('owner', 'tag_category', 'tag_name')]),
        ),
        migrations.RemoveField(
            model_name='drugtag',
            name='drug',
        ),
    ]
