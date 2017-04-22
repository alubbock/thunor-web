import pandas as pd
from .models import WellDrug, WellMeasurement
from django.db.models import Count


class NoDataException(Exception):
    pass


def df_doses_assays_controls(dataset_id, drug_id, cell_line_id,
                             assay, control=None):
    well_info = WellDrug.objects.filter(
        well__plate__dataset_id=dataset_id).annotate(
        num_drugs=Count('well__welldrug')).filter(
        num_drugs=1).select_related('well', 'well__cell_line', 'drug')

    if drug_id:
        well_info = well_info.filter(drug_id=drug_id).order_by(
             'well__cell_line__name', 'dose', 'well__plate_id',
             'well__well_num')

    if cell_line_id:
        well_info = well_info.filter(
            well__cell_line_id=cell_line_id).order_by(
            'drug__name', 'dose', 'well__plate_id', 'well__well_num')

    if control == 'A1':
        well_info = well_info.exclude(well__well_num=0)
    elif control == 0:
        well_info = well_info.exclude(dose=0)

    df_doses = queryset_to_dataframe(
        well_info,
        columns=('dose', 'well_id', 'well__cell_line__name', 'drug__name'),
        rename_columns=('dose', 'well_id', 'cell_line', 'drug'),
        index=('drug', 'cell_line', 'dose'))

    if df_doses.shape[0] == 3 and df_doses.isnull().values.all():
        raise NoDataException()

    timecourses = WellMeasurement.objects.filter(well_id__in=(
        well.well_id for well in well_info), assay=assay).order_by(
        'well_id', 'timepoint')

    df_vals = queryset_to_dataframe(timecourses,
                                    columns=('well_id', 'timepoint', 'value'),
                                    index=('well_id', 'timepoint'))

    if df_vals.shape[0] == 2 and df_vals.isnull().values.all():
        raise NoDataException()

    df_controls = None
    if control is not None:
        controls = WellMeasurement.objects.filter(
            well__plate__dataset_id=dataset_id,
            assay=assay).select_related(
            'well').order_by('well__cell_line', 'timepoint')
        if control == 'A1':
            controls = controls.filter(well__well_num=0)
        elif control == 0:
            controls = WellMeasurement.objects.filter(
                well__welldrug__dose=0,
            ).annotate(
                num_drugs=Count('well__welldrug')).filter(
                num_drugs=1)
        else:
            raise NotImplementedError()

        if cell_line_id:
            controls = controls.filter(well__cell_line_id=cell_line_id)

        df_controls = queryset_to_dataframe(controls,
                                            columns=('well__cell_line__name',
                                                     'well__plate__id',
                                                     'timepoint', 'value'),
                                            rename_columns=('cell_line',
                                                            'plate',
                                                            'timepoint',
                                                            'value'),
                                            index=('cell_line',
                                                   'plate',
                                                   'timepoint'))

    return {'doses': df_doses,
            'assays': df_vals,
            'controls': df_controls}


def queryset_to_dataframe(queryset, columns, index=None, rename_columns=None):
    return pd.DataFrame.from_records(
        (x for x in queryset.values_list(*columns)),
        columns=rename_columns or columns,
        index=index
    )
