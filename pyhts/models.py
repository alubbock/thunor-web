from __future__ import unicode_literals
from django.db import models
from django.conf import settings
from itertools import cycle
from numpy import repeat
from guardian.models import UserObjectPermissionBase, GroupObjectPermissionBase


class HTSDataset(models.Model):
    class Meta:
        permissions = (
            ('view_plots', 'View plots'),
            ('view_plate_layout', 'View plate layout'),
            ('download_data', 'Download data')
        )

    owner = models.ForeignKey(settings.AUTH_USER_MODEL)
    name = models.TextField()
    creation_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return '%s' % self.name

    @classmethod
    def view_dataset_permission_names(cls):
        """
        Currently all permission types allow viewing a dataset
        """
        return [p[0] for p in cls._meta.permissions]


class HTSDatasetUserObjectPermission(UserObjectPermissionBase):
    content_object = models.ForeignKey(HTSDataset)


class HTSDatasetGroupObjectPermission(GroupObjectPermissionBase):
    content_object = models.ForeignKey(HTSDataset)


class PlateFile(models.Model):
    dataset = models.ForeignKey(HTSDataset)
    upload_date = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to='plate-files')
    file_format = models.TextField(null=True)

    def __str__(self):
        return '%s' % self.file.name


class CellLine(models.Model):
    name = models.TextField(unique=True)

    def __str__(self):
        return '%s (%d)' % (self.name, self.id)


class Drug(models.Model):
    name = models.TextField(unique=True)

    def __str__(self):
        return '%s (%d)' % (self.name, self.id)


class PlateMap(object):
    def __init__(self, **kwargs):
        if 'width' in kwargs:
            self.width = kwargs['width']
        if 'height' in kwargs:
            self.height = kwargs['height']
            if self.height > 26:
                # TODO: Fail for now - would need row names like AA, AB etc.
                raise Exception('Plates with height >26 are not yet supported')

    @property
    def num_wells(self):
        return self.width * self.height

    def row_iterator(self):
        return map(chr, range(65, 65 + self.height))

    def col_iterator(self):
        return range(1, self.width + 1)

    def well_id_to_name(self, well_id):
        return '{}{}'.format(chr(65 + (well_id // self.width)),
                             (well_id % self.width) + 1)

    def well_name_to_id(self, well_name, raise_error=True):
        try:
            row_num = ord(well_name[0]) - 65  # zero-based
            if row_num < 0 or row_num > (self.height - 1):
                raise ValueError('Unable to parse well name {} for plate with '
                                 '{} rows'.format(well_name, self.height))

            col_num = int(well_name[1:]) - 1
            if col_num < 0 or col_num > (self.width - 1):
                raise ValueError('Unable to parse well name {} for plate with '
                                 '{} cols'.format(well_name, self.width))

            return row_num * self.width + col_num
        except ValueError as e:
            if raise_error:
                raise e
            else:
                return -1

    def well_iterator(self):
        row_it = iter(repeat(list(self.row_iterator()), self.width))
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
    name = models.TextField()
    last_annotated = models.DateTimeField(null=True)
    width = models.IntegerField()
    height = models.IntegerField()
    expt_id = models.TextField(null=True)
    expt_date = models.DateField(null=True)

    def __str__(self):
        return self.name


class Well(models.Model):
    # __slots__ = ('plate', 'well_num')

    class Meta:
        unique_together = (('plate', 'well_num'), )
        index_together = (('plate', 'well_num'), )

    plate = models.ForeignKey(Plate)
    well_num = models.IntegerField()
    cell_line = models.ForeignKey(CellLine, null=True)


class WellMeasurement(models.Model):
    # __slots__ = ('well', 'assay', 'timepoint', 'value')

    class Meta:
        unique_together = (("well", "assay", "timepoint"), )
        index_together = (("well", "assay", "timepoint"), )

    well = models.ForeignKey(Well)
    assay = models.TextField()
    timepoint = models.DurationField()
    value = models.FloatField(null=True)


class WellDrug(models.Model):
    # __slots__ = ('plate', 'well', 'drug', 'dose')

    class Meta:
        unique_together = (("well", "drug"), ("well", "order"))
        index_together = (("well", "drug", "order"), )

    well = models.ForeignKey(Well)
    drug = models.ForeignKey(Drug, null=True)
    order = models.PositiveSmallIntegerField()
    dose = models.FloatField(null=True)

    def __str__(self):
        return '%.2eM of %s in well %d on plate %s' % (self.dose,
                                                       self.drug.name,
                                                       self.well.well_num,
                                                       self.well.plate.name)
