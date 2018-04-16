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

    owner = models.ForeignKey(settings.AUTH_USER_MODEL)
    name = models.TextField()
    creation_date = models.DateTimeField(auto_now_add=True)
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


class CellLineTag(models.Model):
    class Meta:
        unique_together = (('owner', 'tag_category', 'tag_name',
                            'cell_line'), )

    tag_name = models.TextField()
    tag_category = models.TextField(null=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True)
    cell_line = models.ForeignKey(CellLine)

    @property
    def is_public(self):
        return self.owner is None

    def __str__(self):
        return '%s [%s] (%s)' % (self.tag_name, self.cell_line.name,
                                 self.owner.email if self.owner else
                                 '<public>')

    @classmethod
    def load(cls, filename, owner_id=None):
        import pandas as pd
        csv = pd.read_csv(filename, sep='\t')
        cl_mapping = {cl.name.lower(): cl.id for cl in CellLine.objects.all()}

        csv['cell_line'] = csv['cell_line'].str.lower()

        missing_cls = set(csv['cell_line']).difference(
            cl_mapping.keys())
        if missing_cls:
            print('Cell lines not in DB, skipping: {}'.format(missing_cls))
            csv = csv.loc[~csv['cell_line'].isin(missing_cls), :]

        cls.objects.bulk_create(
            cls(tag_name=row.tag_name,
                tag_category=row.tag_category,
                cell_line_id=cl_mapping[row.cell_line],
                owner=owner_id)
            for row in csv.itertuples())


class Drug(models.Model):
    name = models.TextField(unique=True)

    def __str__(self):
        return '%s (%d)' % (self.name, self.id)


class DrugTag(models.Model):
    class Meta:
        unique_together = (('owner', 'tag_category', 'tag_name',
                            'drug'), )

    tag_name = models.TextField()
    tag_category = models.TextField(null=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True)
    drug = models.ForeignKey(Drug)

    @property
    def is_public(self):
        return self.owner is None

    def __str__(self):
        return '%s [%s] (%s)' % (self.tag_name, self.drug.name,
                                 self.owner.email if self.owner else
                                 '<public>')

    @classmethod
    def load(cls, filename, owner_id=None):
        import pandas as pd
        csv = pd.read_csv(filename, sep='\t')
        drug_mapping = {dr.name.lower(): dr.id for dr in Drug.objects.all()}

        csv['drug'] = csv['drug'].str.lower()

        missing_drugs = set(csv['drug']).difference(
            drug_mapping.keys())
        if missing_drugs:
            print('Drugs not in DB, skipping: {}'.format(missing_drugs))
            csv = csv.loc[~csv['drug'].isin(missing_drugs), :]

        cls.objects.bulk_create(
            cls(tag_name=row.tag_name,
                tag_category=row.tag_category,
                drug_id=drug_mapping[row.drug],
                owner=owner_id)
            for row in csv.itertuples())


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

# Note about indexes: I've removed foreign key indexes for some fields where
# the unique_together constraint has those fields covered by a unique
# constraint, because (in postgres at least) this already creates an index


class Well(models.Model):
    class Meta:
        unique_together = (('plate', 'well_num'), )

    plate = models.ForeignKey(Plate, db_index=False)
    well_num = models.IntegerField()
    cell_line = models.ForeignKey(CellLine, null=True)


class WellMeasurement(models.Model):
    class Meta:
        unique_together = (("well", "assay", "timepoint"), )

    well = models.ForeignKey(Well, db_index=False)
    assay = models.TextField()
    timepoint = models.DurationField()
    value = models.FloatField(null=True)


class WellDrug(models.Model):
    class Meta:
        unique_together = (("well", "drug"), ("well", "order"))

    well = models.ForeignKey(Well, db_index=False)
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
        unique_together = (('well', 'stat_name'), )

    well = models.ForeignKey(Well)
    stat_name = models.TextField()
    stat_date = models.DateTimeField(auto_now=True)
    value = models.FloatField(null=True)


class CurveFit(models.Model):
    stat_type = models.CharField(max_length=10, db_index=True)
    viability_time = models.DurationField(null=True, db_index=True)
    dataset = models.ForeignKey(HTSDataset)
    cell_line = models.ForeignKey(CellLine)
    drug = models.ForeignKey(Drug)
    curve_fit_class = models.CharField(max_length=20, null=True)
    fit_params = models.BinaryField()
    max_dose = models.FloatField()
    min_dose = models.FloatField()
    emax_obs = models.FloatField()
