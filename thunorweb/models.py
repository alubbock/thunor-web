from __future__ import unicode_literals
from django.db import models
from django.conf import settings
from thunor.io import PlateMap
from guardian.models import UserObjectPermissionBase, GroupObjectPermissionBase


class HTSDataset(models.Model):
    class Meta:
        verbose_name = 'HTS Dataset'
        permissions = (
            ('view_plots', 'View plots'),
            ('view_plate_layout', 'View plate layout'),
            ('download_data', 'Download data')
        )

    owner = models.ForeignKey(settings.AUTH_USER_MODEL,
                              on_delete=models.CASCADE)
    name = models.TextField()
    creation_date = models.DateTimeField(auto_now_add=True)
    modified_date = models.DateTimeField(auto_now=True)
    deleted_date = models.DateTimeField(null=True, default=None,
                                        editable=False)

    def __str__(self):
        return '%s (%d)' % (self.name, self.id)

    @classmethod
    def view_dataset_permission_names(cls):
        """
        Currently all permission types allow viewing a dataset
        """
        return [p[0] for p in cls._meta.permissions]

    @classmethod
    def view_dataset_permissions(cls):
        return dict(cls._meta.permissions)

    def add_platefile(self, filename):
        from thunorweb.plate_parsers import PlateFileParser
        from django.core.files import File
        with open(filename, 'rb') as f:
            pfp = PlateFileParser(File(f), dataset=self)
            pfp.parse_all()


class HTSDatasetUserObjectPermission(UserObjectPermissionBase):
    content_object = models.ForeignKey(HTSDataset, on_delete=models.CASCADE)


class HTSDatasetGroupObjectPermission(GroupObjectPermissionBase):
    content_object = models.ForeignKey(HTSDataset, on_delete=models.CASCADE)


class PlateFile(models.Model):
    dataset = models.ForeignKey(HTSDataset, on_delete=models.CASCADE)
    upload_date = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to='plate-files')
    file_format = models.TextField(null=True)

    def __str__(self):
        return '%s' % self.file.name


class CellLine(models.Model):
    name = models.TextField(unique=True)

    def __str__(self):
        return '%s (%d)' % (self.name, self.id)


class CellLineTag(models.Model):
    class Meta:
        unique_together = (('owner', 'tag_category', 'tag_name'), )
        permissions = (
            ('view', 'View tag'),
        )

    tag_name = models.TextField()
    tag_category = models.TextField()
    owner = models.ForeignKey(settings.AUTH_USER_MODEL,
                              on_delete=models.CASCADE)
    cell_lines = models.ManyToManyField(CellLine, related_name='tags')


class CellLineTagGroupObjectPermission(GroupObjectPermissionBase):
    content_object = models.ForeignKey(CellLineTag, on_delete=models.CASCADE)


class Drug(models.Model):
    name = models.TextField(unique=True)

    def __str__(self):
        return '%s (%d)' % (self.name, self.id)


class DrugTag(models.Model):
    class Meta:
        unique_together = (('owner', 'tag_category', 'tag_name'), )
        permissions = (
            ('view', 'View tag'),
        )

    tag_name = models.TextField()
    tag_category = models.TextField()
    owner = models.ForeignKey(settings.AUTH_USER_MODEL,
                              on_delete=models.CASCADE)
    drugs = models.ManyToManyField(Drug, related_name='tags')


class DrugTagGroupObjectPermission(GroupObjectPermissionBase):
    content_object = models.ForeignKey(DrugTag, on_delete=models.CASCADE)


class Plate(models.Model, PlateMap):
    class Meta:
        unique_together = (("dataset", "name"), )

    dataset = models.ForeignKey(HTSDataset, on_delete=models.CASCADE)
    name = models.TextField()
    last_annotated = models.DateTimeField(null=True)
    width = models.IntegerField()
    height = models.IntegerField()
    expt_id = models.TextField(null=True)
    expt_date = models.DateField(null=True)

    def __str__(self):
        if self.name:
            return self.name
        elif self.width and self.height:
            return 'Unnamed {} well plate'.format(self.width * self.height)
        else:
            return 'Unnamed, unsized plate'

# Note about indexes: I've removed foreign key indexes for some fields where
# the unique_together constraint has those fields covered by a unique
# constraint, because (in postgres at least) this already creates an index


class Well(models.Model):
    class Meta:
        unique_together = (('plate', 'well_num'), )

    plate = models.ForeignKey(Plate, db_index=False, on_delete=models.CASCADE)
    well_num = models.IntegerField()
    cell_line = models.ForeignKey(CellLine, null=True, on_delete=models.CASCADE)


class WellMeasurement(models.Model):
    class Meta:
        unique_together = (("well", "assay", "timepoint"), )

    well = models.ForeignKey(Well, db_index=False, on_delete=models.CASCADE)
    assay = models.TextField()
    timepoint = models.DurationField()
    value = models.FloatField(null=True)


class WellDrug(models.Model):
    class Meta:
        unique_together = (("well", "drug"), ("well", "order"))

    well = models.ForeignKey(Well, db_index=False, on_delete=models.CASCADE)
    drug = models.ForeignKey(Drug, null=True, on_delete=models.CASCADE)
    order = models.PositiveSmallIntegerField()
    dose = models.FloatField(null=True)

    def __str__(self):
        return '%.2eM of %s in well %d on plate %s' % (self.dose,
                                                       self.drug.name,
                                                       self.well.well_num,
                                                       self.well.plate.name)


class WellStatistic(models.Model):
    class Meta:
        unique_together = (('well', 'stat_name'), )

    well = models.ForeignKey(Well, on_delete=models.CASCADE)
    stat_name = models.TextField()
    stat_date = models.DateTimeField(auto_now=True)
    value = models.FloatField(null=True)


class CurveFitSet(models.Model):
    class Meta:
        unique_together = (('dataset', 'stat_type', 'viability_time'), )

    dataset = models.ForeignKey(HTSDataset, on_delete=models.CASCADE)
    stat_type = models.CharField(max_length=10)
    viability_time = models.DurationField()
    fit_protocol = models.IntegerField()
    calculation_start = models.DateTimeField()
    calculation_end = models.DateTimeField(null=True)

    def __str__(self):
        return '{} on dataset {}'.format(self.stat_type, self.dataset)


class CurveFit(models.Model):
    class Meta:
        unique_together = (('fit_set', 'cell_line', 'drug'), )

    fit_set = models.ForeignKey(CurveFitSet, on_delete=models.CASCADE)
    cell_line = models.ForeignKey(CellLine, on_delete=models.CASCADE)
    drug = models.ForeignKey(Drug, on_delete=models.CASCADE)
    curve_fit_class = models.CharField(max_length=20, null=True)
    fit_params = models.BinaryField()
    max_dose = models.FloatField()
    min_dose = models.FloatField()
    emax_obs = models.FloatField()
    aa_obs = models.FloatField(null=True)


class HTSDatasetFile(models.Model):
    class Meta:
        unique_together = (('dataset', 'file_type'), )

    dataset = models.ForeignKey(HTSDataset, on_delete=models.CASCADE)
    file_type = models.TextField()
    file_type_protocol = models.IntegerField()
    file = models.FileField()
    creation_date = models.DateTimeField(auto_now_add=True)
