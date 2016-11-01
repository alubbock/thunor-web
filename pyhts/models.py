from __future__ import unicode_literals
from django.db import models
from django.conf import settings


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


class Plate(models.Model):
    class Meta:
        unique_together = (("dataset", "plate_file"), )

    dataset = models.ForeignKey(HTSDataset)
    plate_file = models.ForeignKey(PlateFile)
    plate_name = models.TextField()
    plate_size = models.IntegerField()
    timepoint_secs = models.IntegerField()


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
