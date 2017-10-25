import pandas as pd
from .models import Well, WellDrug, WellMeasurement, WellStatistic
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

    # Filter by dataset
    if isinstance(dataset_id, Iterable):
        well_info_base = Well.objects.filter(
            plate__dataset_id__in=dataset_id
        )
    else:
        well_info_base = Well.objects.filter(
            plate__dataset_id=dataset_id
        )

    # well_info = well_info.annotate(num_drugs=Count('well__welldrug')).filter(
    #     num_drugs=1)

    # Filter by cell line

    # well_info = _add_int_or_list_filter(well_info, 'drug_id', drug_id)
    well_info_base = _add_int_or_list_filter(well_info_base,
                                             'cell_line_id',
                                             cell_line_id)

    well_info_base = well_info_base.annotate(num_drugs=Count('welldrug'))

    # Filter control wells (these are fetched separately)
    well_info_base = well_info_base.annotate(max_dose=Max(
        'welldrug__dose')).filter(max_dose__gt=0)

    drug_ids_single = []
    drug_ids_combo = []

    if isinstance(drug_id, Iterable):
        for dr_id in drug_id:
            if isinstance(dr_id, int):
                drug_ids_single.append(dr_id)
            else:
                drug_ids_combo.append(dr_id)
    else:
        drug_ids_single = drug_id

    # Query for single drug wells
    well_info = _add_int_or_list_filter(well_info_base, 'welldrug__drug_id',
                                        drug_ids_single)
    if drug_id is not None:
        well_info = well_info.filter(num_drugs=1)

    # Query for multi-drug wells
    for drug_combo in drug_ids_combo:
        this_query = well_info_base
        for drug in drug_combo:
            this_query = this_query.filter(welldrug__drug_id=drug)
        this_query = this_query.filter(num_drugs=len(drug_combo))
        well_info |= this_query

    if drug_id and not cell_line_id:
            well_info = well_info.order_by(
             'cell_line__name', 'plate__dataset_id', 'plate_id',
             'well_num')

    return well_info, drug_id, cell_line_id


def _apply_control_filter(queryset, cell_line_id):
    queryset = queryset.annotate(max_dose=Max(
        'well__welldrug__dose')).filter(max_dose=0)

    return _add_int_or_list_filter(queryset, 'well__cell_line_id',
                                   cell_line_id)


def _dataframe_wellinfo(dataset_id, drug_id, cell_line_id,
                        use_dataset_names=False):
    well_info, drug_id, cell_line_id = _queryset_well_info(
        dataset_id, drug_id, cell_line_id)

    well_info = well_info.prefetch_related('welldrug_set',
                                           'welldrug_set__drug')
    well_info = well_info.select_related('cell_line', 'plate')
    if use_dataset_names:
        well_info = well_info.prefetch_related('plate__dataset')

    x = []
    for well in well_info:
        vals = [(d.drug.name, d.dose) for d in well.welldrug_set.all()]
        if vals:
            names, doses = zip(*vals)

            x.append({'dose': doses, 'well_id': well.id,
             'cell_line': well.cell_line.name, 'drug': names, 'plate_id':
                 well.plate_id,
                      'dataset': dataset_id if not isinstance(dataset_id,
                                                              Iterable)\
                          and not use_dataset_names
                      else (well.plate.dataset.name if use_dataset_names else
                     well.plate.dataset_id)})

    df_doses = pd.DataFrame(x)
    df_doses.set_index(keys=['dataset', 'drug', 'cell_line', 'dose'],
                       inplace=True)

    return df_doses


def df_doses_assays_controls(dataset, drug_id, cell_line_id, assay):
    dataset_id = dataset.id

    well_info, drug_id, cell_line_id = _queryset_well_info(
        dataset_id, drug_id, cell_line_id)

    df_doses = _dataframe_wellinfo(dataset_id, drug_id, cell_line_id)

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
    dip_stats = ('dip_rate', 'dip_fit_std_err')

    dataset_id_field = 'well__plate__dataset' + ('__name' if
                                                 use_dataset_names else '_id')

    df_doses = _dataframe_wellinfo(dataset_id, drug_id, cell_line_id,
                                   use_dataset_names=use_dataset_names)

    # df_doses = queryset_to_dataframe(
    #     WellStatistic.objects.filter(
    #         well_id__in=well_info.values_list('well_id'),
    #         stat_name__in=dip_stats,
    #     ),
    #     columns=('stat_name', 'value', 'well__welldrug__dose', 'well_id',
    #              'well__cell_line__name', 'well__welldrug__drug__name',
    #              dataset_id_field),
    #     rename_columns=('stat_name', 'value', 'dose', 'well_id', 'cell_line',
    #                     'drug', 'dataset')
    # )

    if df_doses['well_id'].isnull().all():
        raise NoDataException()

    well_stats = queryset_to_dataframe(
        WellStatistic.objects.filter(
            well_id__in=df_doses['well_id'],
            stat_name__in=dip_stats,
        ),
        columns=('well_id', 'stat_name', 'value'),
        index=('well_id', 'stat_name')
    )

    if well_stats.isnull().values.all():
        raise NoDataException

    well_stats = well_stats.pivot_table(index='well_id', columns='stat_name',
                                        values='value')

    df_doses = pd.merge(df_doses, well_stats, left_on='well_id',
                        right_index=True)

    # plate_ids = df_doses['plate_id'].unique()
    # del df_doses['plate_id']

    # df_doses = df_doses.pivot_table(
    #     index=('dataset', 'drug', 'cell_line', 'dose', 'well_id'),
    #     columns='stat_name', values=['value'])['value']

    # controls = WellStatistic.objects.filter(stat_name__in=dip_stats)
    # if isinstance(dataset_id, Iterable):
    #     controls = controls.filter(well__plate__dataset_id__in=dataset_id)
    # else:
    #     controls = controls.filter(well__plate__dataset_id=dataset_id)
    # controls = _apply_control_filter(controls, cell_line_id)
    #
    # df_controls = queryset_to_dataframe(
    #     controls,
    #     columns=(dataset_id_field, 'well__cell_line__name',
    #              'well_id', 'stat_name', 'value'),
    #     rename_columns=('dataset', 'cell_line', 'well_id', 'stat_name',
    #                     'value')
    # )
    #
    # if df_controls.isnull().values.all():
    #     df_controls = None
    # else:
    #     df_controls = df_controls.pivot_table(
    #         index=('dataset', 'cell_line', 'well_id'),
    #         columns='stat_name', values=['value'])['value']

    controls = WellStatistic.objects.filter(stat_name__in=dip_stats,)
    if isinstance(dataset_id, Iterable):
        controls = controls.filter(well__plate__dataset_id__in=dataset_id)
    else:
        controls = controls.filter(well__plate__dataset_id=dataset_id)
    controls = _apply_control_filter(controls, cell_line_id)

    df_controls = queryset_to_dataframe(
        controls,
        columns=(dataset_id_field, 'well__cell_line__name', 'well_id',
                 'stat_name', 'value'),
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
