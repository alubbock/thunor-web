# -*- coding: utf-8 -*-
# Generated by Django 1.10.1 on 2016-10-31 21:59
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pyhts', '0002_auto_20161031_2014'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='platefile',
            name='owner',
        ),
        migrations.AddField(
            model_name='platefile',
            name='dataset',
            field=models.ForeignKey(default=0, on_delete=django.db.models.deletion.CASCADE, to='pyhts.HTSDataset'),
            preserve_default=False,
        ),
    ]