# -*- coding: utf-8 -*-
# Generated by Django 1.11.10 on 2018-04-19 22:24
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
import collections


def move_drug_to_drugs(apps, schema_editor):
    # Convert from foreign key to many-to-many field
    DrugTag = apps.get_model('thunorweb.DrugTag')

    tag_details = collections.defaultdict(set)

    for dt in DrugTag.objects.all():
        tag_details[dt.owner_id, dt.tag_category, dt.tag_name].add(
            dt.drug_id
        )

    if tag_details:
        tags = []
        for tag in tag_details:
            tags.append(DrugTag(
                owner_id=tag[0],
                tag_category=tag[1],
                tag_name=tag[2]
            ))

        DrugTag.objects.all().delete()
        DrugTag.objects.bulk_create(tags)
        if tags[0].pk is None:
            tags = DrugTag.objects.all()

        for tag in tags:
            tag.drugs.add(*tag_details[tag.owner_id, tag.tag_category,
                                       tag.tag_name])


def move_cell_line_to_cell_lines(apps, schema_editor):
    # Convert from foreign key to many-to-many field
    CellLineTag = apps.get_model('thunorweb.CellLineTag')

    tag_details = collections.defaultdict(set)

    for clt in CellLineTag.objects.all():
        tag_details[clt.owner_id, clt.tag_category, clt.tag_name].add(
            clt.cell_line_id
        )

    if tag_details:
        tags = []
        for tag in tag_details:
            tags.append(CellLineTag(
                owner_id=tag[0],
                tag_category=tag[1],
                tag_name=tag[2]
            ))

        CellLineTag.objects.all().delete()
        CellLineTag.objects.bulk_create(tags)
        if tags[0].pk is None:
            tags = CellLineTag.objects.all()

        for tag in tags:
            tag.cell_lines.add(*tag_details[tag.owner_id, tag.tag_category,
                                            tag.tag_name])


class Migration(migrations.Migration):

    dependencies = [
        ('thunorweb', '0008_curvefit_squashed_0009_auto_20180409_0505'),
    ]

    operations = [
        migrations.AddField(
            model_name='celllinetag',
            name='cell_lines',
            field=models.ManyToManyField(related_name='tags', to='thunorweb.CellLine'),
        ),
        migrations.AddField(
            model_name='drugtag',
            name='drugs',
            field=models.ManyToManyField(related_name='tags', to='thunorweb.Drug'),
        ),
        migrations.AlterField(
            model_name='celllinetag',
            name='cell_line',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='thunorweb.CellLine'),
        ),
        migrations.AlterField(
            model_name='drugtag',
            name='drug',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='thunorweb.Drug'),
        ),
        migrations.RunPython(move_drug_to_drugs),
        migrations.RunPython(move_cell_line_to_cell_lines)
    ]