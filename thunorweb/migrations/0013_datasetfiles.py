# -*- coding: utf-8 -*-
# Generated by Django 1.11.10 on 2018-04-26 17:50
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('thunorweb', '0012_curvefitset'),
    ]

    operations = [
        migrations.CreateModel(
            name='HTSDatasetFile',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file_type', models.TextField()),
                ('file_type_protocol', models.IntegerField()),
                ('file', models.FileField(upload_to='')),
                ('creation_date', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.AddField(
            model_name='htsdataset',
            name='modified_date',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterUniqueTogether(
            name='curvefit',
            unique_together=set([('fit_set', 'cell_line', 'drug')]),
        ),
        migrations.AddField(
            model_name='htsdatasetfile',
            name='dataset',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='thunorweb.HTSDataset'),
        ),
        migrations.AlterUniqueTogether(
            name='htsdatasetfile',
            unique_together=set([('dataset', 'file_type')]),
        ),
    ]
