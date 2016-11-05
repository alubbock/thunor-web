from __future__ import unicode_literals
from django.db import models
from django.conf import settings
from itertools import cycle
from numpy import repeat
from helpers import guess_timepoint_hrs
from plate_parsers import parse_platefile_readerX


class HTSDataset(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL)
    name = models.TextField()
    creation_date = models.DateTimeField(auto_now_add=True)


class PlateFile(models.Model):
    dataset = models.ForeignKey(HTSDataset)
    upload_date = models.DateTimeField(auto_now_add=True)
    process_date = models.DateTimeField(null=True, blank=True)
    file = models.FileField()

    def read(self, quick_parse=False):
        self.file.seek(0)
        pd = self.file.read()
        file_timepoint_guess = guess_timepoint_hrs(self.file.name)
        return parse_platefile_readerX(pd,
                                       quick_parse=quick_parse,
                                       file_timepoint_guess_hrs=file_timepoint_guess,
                                       )


class CellLine(models.Model):
    name = models.TextField(unique=True)


class Drug(models.Model):
    name = models.TextField(unique=True)


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


class WellCellLine(models.Model):
    __slots__ = ('plate', 'well')

    class Meta:
        unique_together = (("plate", "well"), )

    plate = models.ForeignKey(Plate)
    well = models.IntegerField()
    cell_line = models.ForeignKey(CellLine, null=True)


class WellMeasurement(models.Model):
    __slots__ = ('plate', 'well', 'assay', 'value')

    class Meta:
        unique_together = (("plate", "well", "assay"), )

    plate = models.ForeignKey(Plate)
    well = models.IntegerField()
    assay = models.TextField()
    value = models.FloatField()


class WellDrug(models.Model):
    __slots__ = ('plate', 'well', 'drug', 'dose')

    class Meta:
        unique_together = (("plate", "well", "drug"), )

    plate = models.ForeignKey(Plate)
    well = models.IntegerField()
    drug = models.ForeignKey(Drug)
    dose = models.FloatField()
