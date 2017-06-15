import pandas as pd
from .models import WellDrug, WellMeasurement
from django.db.models import Count
from collections import Iterable


class NoDataException(Exception):
    pass


def df_doses_assays_controls(dataset_id, drug_id, cell_line_id,
                             assay, control=None):
    if isinstance(drug_id, Iterable) and len(drug_id) == 1:
        drug_id = drug_id[0]
    if isinstance(cell_line_id, Iterable) and len(cell_line_id) == 1:
        cell_line_id = cell_line_id[0]

    well_info = WellDrug.objects.filter(
        well__plate__dataset_id=dataset_id).annotate(
        num_drugs=Count('well__welldrug')).filter(
        num_drugs=1)

    if drug_id:
        if isinstance(drug_id, int):
            well_info = well_info.filter(drug_id=drug_id)
        elif isinstance(drug_id, Iterable):
            well_info = well_info.filter(drug_id__in=drug_id)
        else:
            raise NotImplementedError()

        if not cell_line_id:
            well_info = well_info.order_by(
             'well__cell_line__name', 'dose', 'well__plate_id',
             'well__well_num')

    if cell_line_id:
        if isinstance(cell_line_id, int):
            well_info = well_info.filter(well__cell_line_id=cell_line_id)
        elif isinstance(cell_line_id, Iterable):
            well_info = well_info.filter(well__cell_line_id__in=cell_line_id)
        else:
            raise NotImplementedError()

    if control == 'A1':
        well_info = well_info.exclude(well__well_num=0)
    elif control == 0:
        well_info = well_info.exclude(dose=0)

    df_doses = queryset_to_dataframe(
        well_info,
        columns=('dose', 'well_id', 'well__cell_line__name', 'drug__name',
                 'well__plate_id'),
        rename_columns=('dose', 'well_id', 'cell_line', 'drug', 'plate_id'),
        index=('drug', 'cell_line', 'dose'))

    plate_ids = df_doses['plate_id'].unique()
    del df_doses['plate_id']

    if df_doses.shape[0] == 3 and df_doses.isnull().values.all():
        raise NoDataException()

    timecourses = WellMeasurement.objects.filter(
        well_id__in=df_doses['well_id'].unique(), assay=assay).order_by(
        'well_id', 'timepoint')

    df_vals = queryset_to_dataframe(timecourses,
                                    columns=('well_id', 'timepoint', 'value'),
                                    index=('well_id', 'timepoint'))

    if df_vals.shape[0] == 2 and df_vals.isnull().values.all():
        raise NoDataException()

    df_controls = None
    if control is not None:
        controls = WellMeasurement.objects.filter(
            well__plate_id__in=plate_ids,
            assay=assay).select_related(
            'well').order_by('well__cell_line', 'timepoint')
        if control == 'A1':
            controls = controls.filter(well__well_num=0)
        elif control == 0:
            controls = controls.filter(
                well__welldrug__dose=0,
            ).annotate(
                num_drugs=Count('well__welldrug')).filter(
                num_drugs=1)
        else:
            raise NotImplementedError()

        if cell_line_id and isinstance(cell_line_id, int):
            controls = controls.filter(well__cell_line_id=cell_line_id)
        elif cell_line_id and isinstance(cell_line_id, Iterable):
            controls = controls.filter(well__cell_line_id__in=cell_line_id)

        df_controls = queryset_to_dataframe(controls,
                                            columns=('well__cell_line__name',
                                                     'well__plate__id',
                                                     'well_id',
                                                     'timepoint',
                                                     'value'),
                                            rename_columns=('cell_line',
                                                            'plate',
                                                            'well_id',
                                                            'timepoint',
                                                            'value'),
                                            index=('cell_line',
                                                   'plate',
                                                   'well_id',
                                                   'timepoint'))

        if df_controls.shape[0] == 4 and df_controls.isnull().values.all():
            df_controls = None

    return {'doses': df_doses,
            'assays': df_vals,
            'controls': df_controls}


def queryset_to_dataframe(queryset, columns, index=None, rename_columns=None):
    return pd.DataFrame.from_records(
        queryset.values_list(*columns).iterator(),
        columns=rename_columns or columns,
        index=index
    )
