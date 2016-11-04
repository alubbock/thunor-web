from __future__ import unicode_literals
from django.db import models
from django.conf import settings
from itertools import cycle
from numpy import repeat


class HTSDataset(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL)
    name = models.TextField()
    creation_date = models.DateTimeField(auto_now_add=True)


class PlateFile(models.Model):
    dataset = models.ForeignKey(HTSDataset)
    upload_date = models.DateTimeField(auto_now_add=True)
    process_date = models.DateTimeField(null=True, blank=True)
    file = models.FileField()


class CellLine(models.Model):
    name = models.TextField(unique=True)

    @classmethod
    def name_list(cls):
        return list(cls.objects.order_by('name').values_list('name',
                                                             flat=True))


class Drug(models.Model):
    name = models.TextField(unique=True)

    @classmethod
    def name_list(cls):
        return list(cls.objects.order_by('name').values_list('name',
                                                             flat=True))


class PlateMap(object):
    def __init__(self, *args, **kwargs):
        if 'width' in kwargs:
            self.width = kwargs['width']
        if 'height' in kwargs:
            self.height = kwargs['height']

    @property
    def num_wells(self):
        return self.width * self.height

    def row_iterator(self):
        if self.height > 26:
            raise Exception('Cannot currently handle well plates > 26 rows')
        return map(chr, range(65, 65 + self.height))

    def col_iterator(self):
        return range(1, self.width + 1)

    def well_iterator(self):
        row_it = iter(repeat(self.row_iterator(), self.width))
        col_it = cycle(self.col_iterator())
        for i in range(self.num_wells):
            yield {'well': i,
                   'row': row_it.next(),
                   'col': col_it.next()}


class Plate(models.Model, PlateMap):
    plate_file = models.ForeignKey(PlateFile)
    name = models.TextField()
    width = models.IntegerField()
    height = models.IntegerField()
    timepoint_secs = models.IntegerField(null=True)


class PlateAssay(models.Model):
    class Meta:
        unique_together = (("plate", "assay"), )

    plate = models.ForeignKey(Plate)
    assay = models.TextField()


class Well(models.Model):
    __slots__ = ('plate_assay', 'well_no')

    class Meta:
        unique_together = (("plate_assay", "well_no"), )

    plate_assay = models.ForeignKey(PlateAssay)
    well_no = models.IntegerField()


class DrugInWell(models.Model):
    __slots__ = ('well', 'drug', 'dose')

    class Meta:
        unique_together = (("well", "drug"), )

    well = models.ForeignKey(Well)
    drug = models.ForeignKey(Drug)
    dose = models.FloatField()
