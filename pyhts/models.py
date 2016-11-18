from __future__ import unicode_literals
from django.db import models
from django.conf import settings
from itertools import cycle
from numpy import repeat


class HTSDataset(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL)
    name = models.TextField()
    creation_date = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def get_plate_file_ids(id):
        return [p['id'] for p in Plate.objects.filter(
            plate_file__dataset_id=id).order_by(
            'plate_file_id', 'id').values('id')]

    @property
    def plate_file_ids(self):
        return self.get_plate_file_ids(self.id)


class PlateFile(models.Model):
    dataset = models.ForeignKey(HTSDataset)
    upload_date = models.DateTimeField(auto_now_add=True)
    file = models.FileField()
    file_format = models.TextField(null=True)


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
        row_it = iter(repeat(list(self.row_iterator()), self.width))
        # print(row_it)
        # print(next(next(row_it)))
        col_it = cycle(self.col_iterator())
        for i in range(self.num_wells):
            yield {'well': i,
                   'row': next(row_it),
                   'col': next(col_it)}

    def well_list(self):
        return list(self.well_iterator())


class Plate(models.Model, PlateMap):
    class Meta:
        unique_together = (("dataset", "name"), )

    dataset = models.ForeignKey(HTSDataset)
    plate_file = models.ForeignKey(PlateFile)
    name = models.TextField()
    last_annotated = models.DateTimeField(null=True)
    width = models.IntegerField()
    height = models.IntegerField()

    @property
    def next_plate_id(self):
        pf_ids = HTSDataset.get_plate_file_ids(self.dataset_id)
        idx = pf_ids.index(self.id) + 1
        return idx if idx < (len(pf_ids) - 1) else None


class WellMeasurement(models.Model):
    __slots__ = ('plate', 'well', 'assay', 'timepoint', 'value')

    class Meta:
        unique_together = (("plate", "well", "assay", "timepoint"), )

    plate = models.ForeignKey(Plate)
    well = models.IntegerField()
    assay = models.TextField()
    timepoint = models.DurationField()
    value = models.FloatField(null=True)


class WellCellLine(models.Model):
    __slots__ = ('plate', 'well')

    class Meta:
        unique_together = (("plate", "well"), )

    plate = models.ForeignKey(Plate)
    well = models.IntegerField()
    cell_line = models.ForeignKey(CellLine, null=True)


class WellDrug(models.Model):
    __slots__ = ('plate', 'well', 'drug', 'dose')

    class Meta:
        unique_together = (("plate", "well", "drug"), )

    plate = models.ForeignKey(Plate)
    well = models.IntegerField()
    drug = models.ForeignKey(Drug)
    dose = models.FloatField()
