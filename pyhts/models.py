from __future__ import unicode_literals
from django.db import models
from django.conf import settings
from pydrc.io import PlateMap
from guardian.models import UserObjectPermissionBase, GroupObjectPermissionBase


class HTSDataset(models.Model):
    class Meta:
        permissions = (
            ('view_plots', 'View plots'),
            ('view_plate_layout', 'View plate layout'),
            ('download_data', 'Download data')
        )
    CONTROL_CHOICES = (
        (None, 'Unspecified'),
        ('A1', 'Well A1')
    )

    owner = models.ForeignKey(settings.AUTH_USER_MODEL)
    name = models.TextField()
    creation_date = models.DateTimeField(auto_now_add=True)
    control_handling = models.TextField(null=True, choices=CONTROL_CHOICES)

    def __str__(self):
        return '%s (%d)' % (self.name, self.id)

    # def cell_lines(self):
    #     return CellLine.objects.filter(
    #         well__plate__dataset_id=self.id).distinct().order_by('id')
    #
    # def drugs(self):
    #     return Drug.objects.filter(
    #         welldrug__well__plate__dataset_id=self.id).distinct().order_by(
    #         'id')
    #
    # @property
    # def last_annotated(self):
    #     try:
    #         return max([p.last_annotated for p in self.plates.all() if
    #                     p.last_annotated is not None])
    #     except ValueError:
    #         return None
    #     # return self.plates.aggregate(last_annotated=models.Max(
    #     #     'last_annotated'))['last_annotated']

    @classmethod
    def view_dataset_permission_names(cls):
        """
        Currently all permission types allow viewing a dataset
        """
        return [p[0] for p in cls._meta.permissions]

    @property
    def dip_assay(self):
        if self.control_handling == 'A1':
            assay = 'Cell count'
        elif self.control_handling is None:
            # TODO: Better detection of cell count proxy assay
            assay = 'lum:Lum'
        else:
            raise ValueError('Unknown control handling: ' +
                             self.control_handling)

        return assay

    @property
    def control_id(self):
        if self.control_handling == 'A1':
            control_id = 'A1'
        elif self.control_handling is None:
            control_id = 0
        else:
            raise ValueError('Unknown control handling: ' +
                             self.control_handling)

        return control_id


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
        return '%d: %s' % (self.id, self.name)


class CellLineTag(models.Model):
    class Meta:
        unique_together = (('tag_name', 'owner', 'cell_line'), )
        index_together = (('tag_name', 'owner', 'cell_line'), )

    tag_name = models.TextField()
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True)
    cell_line = models.ForeignKey(CellLine)

    def __str__(self):
        return '%s [%s] (%s)' % (self.tag_name, self.cell_line.name,
                                 self.owner.email)


class Drug(models.Model):
    name = models.TextField(unique=True)

    def __str__(self):
        return '%d: %s' % (self.id, self.name)


class DrugTag(models.Model):
    class Meta:
        unique_together = (('tag_name', 'owner', 'drug'), )
        index_together = (('tag_name', 'owner', 'drug'), )

    tag_name = models.TextField()
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True)
    drug = models.ForeignKey(Drug)

    def __str__(self):
        return '%s [%s] (%s)' % (self.tag_name, self.drug.name,
                                 self.owner.email)


class Plate(models.Model, PlateMap):
    class Meta:
        unique_together = (("dataset", "name"), )

    dataset = models.ForeignKey(HTSDataset, related_name='plates')
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

    plate = models.ForeignKey(Plate, related_name='wells')
    well_num = models.IntegerField()
    cell_line = models.ForeignKey(CellLine, null=True)


class WellMeasurement(models.Model):
    # __slots__ = ('well', 'assay', 'timepoint', 'value')

    class Meta:
        unique_together = (("well", "assay", "timepoint"), )
        index_together = (("well", "assay", "timepoint"), )

    well = models.ForeignKey(Well, related_name='data')
    assay = models.TextField()
    timepoint = models.DurationField()
    value = models.FloatField(null=True)


class WellDrug(models.Model):
    # __slots__ = ('plate', 'well', 'drug', 'dose')

    class Meta:
        unique_together = (("well", "drug"), ("well", "order"))
        index_together = (("well", "drug", "order"), )

    well = models.ForeignKey(Well, related_name='drugs')
    drug = models.ForeignKey(Drug, null=True)
    order = models.PositiveSmallIntegerField()
    dose = models.FloatField(null=True)

    def __str__(self):
        return '%.2eM of %s in well %d on plate %s' % (self.dose,
                                                       self.drug.name,
                                                       self.well.well_num,
                                                       self.well.plate.name)


class WellStatistic(models.Model):
    class Meta:
        pass

    well = models.ForeignKey(Well)
    stat_name = models.TextField()
    stat_date = models.DateTimeField(auto_now=True)
    value = models.FloatField(null=True)
