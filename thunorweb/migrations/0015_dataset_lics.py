# -*- coding: utf-8 -*-
# Generated by Django 1.11.22 on 2019-07-23 00:01
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('thunorweb', '0014_aa_obs'),
    ]

    operations = [
        migrations.AddField(
            model_name='htsdataset',
            name='creator',
            field=models.TextField(null=True),
        ),
        migrations.AddField(
            model_name='htsdataset',
            name='license_text',
            field=models.TextField(null=True),
        ),
    ]