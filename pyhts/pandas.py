import pandas as pd
from .models import WellDrug, WellMeasurement, WellStatistic
from django.db.models import Count, Max
from collections import Iterable
from pydrc.io import HtsPandas


class NoDataException(Exception):
    pass


def _add_int_or_list_filter(queryset, field_name, field_value):
    if field_value is None:
        return queryset
    if isinstance(field_value, int):
        return queryset.filter(**{field_name: field_value})
    if isinstance(field_value, Iterable):
        return queryset.filter(**{'{}__in'.format(field_name): field_value})

    raise NotImplementedError()


def _queryset_well_info(dataset_id, drug_id, cell_line_id):
    drug_id = drug_id[0] if isinstance(drug_id, Iterable) and \
        len(drug_id) == 1 else drug_id
    cell_line_id = cell_line_id[0] if isinstance(cell_line_id, Iterable) and \
        len(cell_line_id) == 1 else cell_line_id

    if isinstance(dataset_id, Iterable):
        well_info = WellDrug.objects.filter(
            well__plate__dataset_id__in=dataset_id
        )
    else:
        well_info = WellDrug.objects.filter(
            well__plate__dataset_id=dataset_id
        )

    well_info = well_info.annotate(num_drugs=Count('well__welldrug')).filter(
        num_drugs=1)

    well_info = _add_int_or_list_filter(well_info, 'drug_id', drug_id)
    well_info = _add_int_or_list_filter(well_info, 'well__cell_line_id',
                                        cell_line_id)

    if drug_id and not cell_line_id:
            well_info = well_info.order_by(
             'well__cell_line__name', 'dose', 'well__plate_id',
             'well__well_num')

    well_info = well_info.annotate(max_dose=Max(
        'well__welldrug__dose')).filter(max_dose__gt=0)

    return well_info, drug_id, cell_line_id


def _apply_control_filter(queryset, cell_line_id):
    queryset = queryset.annotate(max_dose=Max(
        'well__welldrug__dose')).filter(max_dose=0)

    return _add_int_or_list_filter(queryset, 'well__cell_line_id',
                                   cell_line_id)


def df_doses_assays_controls(dataset, drug_id, cell_line_id, assay):
    dataset_id = dataset.id

    well_info, drug_id, cell_line_id = _queryset_well_info(
        dataset_id, drug_id, cell_line_id)

    df_doses = queryset_to_dataframe(
        well_info,
        columns=('dose', 'well_id', 'well__cell_line__name', 'drug__name'),
        rename_columns=('dose', 'well_id', 'cell_line', 'drug'),
        index=('drug', 'cell_line', 'dose'))

    if df_doses.shape[0] == 3 and df_doses.isnull().values.all():
        raise NoDataException()

    timecourses = WellMeasurement.objects.filter(
        well_id__in=df_doses['well_id'].unique()).order_by(
        'well_id', 'timepoint')

    if assay is not None:
        timecourses = timecourses.filter(assay=assay)

    df_vals = queryset_to_dataframe(
        timecourses,
        columns=('assay', 'well_id', 'timepoint', 'value'),
        index=('assay', 'well_id', 'timepoint'))

    if df_vals.isnull().values.all():
        raise NoDataException()

    controls = WellMeasurement.objects.filter(
        well__plate__dataset_id=dataset_id).select_related(
        'well').order_by('well__cell_line', 'timepoint')
    if assay is not None:
        controls = controls.filter(assay=assay)
    controls = _apply_control_filter(controls, cell_line_id)

    df_controls = queryset_to_dataframe(controls,
                                        columns=('assay',
                                                 'well__cell_line__name',
                                                 'well__plate__id',
                                                 'well_id',
                                                 'timepoint',
                                                 'value'),
                                        rename_columns=('assay',
                                                        'cell_line',
                                                        'plate',
                                                        'well_id',
                                                        'timepoint',
                                                        'value'),
                                        index=('assay',
                                               'cell_line',
                                               'plate',
                                               'well_id',
                                               'timepoint'))

    if df_controls.isnull().values.all():
        df_controls = None

    return HtsPandas(df_doses, df_vals, df_controls)


def df_dip_rates(dataset_id, drug_id, cell_line_id,
                 use_dataset_names=False):
    well_info, drug_id, cell_line_id = _queryset_well_info(
        dataset_id, drug_id, cell_line_id)

    dip_stats = ('dip_rate', 'dip_fit_std_err')

    dataset_id_field = 'well__plate__dataset' + ('__name' if
                                                 use_dataset_names else '_id')

    df_doses = queryset_to_dataframe(
        WellStatistic.objects.filter(
            well_id__in=well_info.values_list('well_id'),
            stat_name__in=dip_stats,
        ),
        columns=('stat_name', 'value', 'well__welldrug__dose', 'well_id',
                 'well__cell_line__name', 'well__welldrug__drug__name',
                 dataset_id_field),
        rename_columns=('stat_name', 'value', 'dose', 'well_id', 'cell_line',
                        'drug', 'dataset')
    )

    if df_doses.isnull().values.all():
        raise NoDataException()

    df_doses = df_doses.pivot_table(
        index=('dataset', 'drug', 'cell_line', 'dose', 'well_id'),
        columns='stat_name', values=['value'])['value']

    controls = WellStatistic.objects.filter(stat_name__in=dip_stats)
    if isinstance(dataset_id, Iterable):
        controls = controls.filter(well__plate__dataset_id__in=dataset_id)
    else:
        controls = controls.filter(well__plate__dataset_id=dataset_id)
    controls = _apply_control_filter(controls, cell_line_id)

    df_controls = queryset_to_dataframe(
        controls,
        columns=(dataset_id_field, 'well__cell_line__name',
                 'well_id', 'stat_name', 'value'),
        rename_columns=('dataset', 'cell_line', 'well_id', 'stat_name',
                        'value')
    )

    if df_controls.isnull().values.all():
        df_controls = None
    else:
        df_controls = df_controls.pivot_table(
            index=('dataset', 'cell_line', 'well_id'),
            columns='stat_name', values=['value'])['value']

    return df_controls, df_doses


def queryset_to_dataframe(queryset, columns, index=None, rename_columns=None):
    return pd.DataFrame.from_records(
        queryset.values_list(*columns).iterator(),
        columns=rename_columns or columns,
        index=index
    )
