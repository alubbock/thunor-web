# -*- coding: utf-8 -*-
# Generated by Django 1.11.2 on 2017-06-29 21:32
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pyhts', '0008_well_statistics'),
    ]

    operations = [
        migrations.AlterField(
            model_name='wellstatistic',
            name='value',
            field=models.FloatField(null=True),
        ),
    ]