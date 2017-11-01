import pandas as pd
from .models import Well, WellDrug, WellMeasurement, WellStatistic
from django.db.models import Count, Max, Sum
from django.db.models.functions import Coalesce
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


def _queryset_well_ids(dataset_id, drug_id, cell_line_id):
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

    return well_info


def _queryset_well_info(dataset_id, drug_id, cell_line_id,
                        only_need_ids=False):
    # drug_id = drug_id[0] if isinstance(drug_id, Iterable) and \
    #     len(drug_id) == 1 else drug_id
    cell_line_id = cell_line_id[0] if isinstance(cell_line_id, Iterable) and \
        len(cell_line_id) == 1 else cell_line_id

    if not is_multi_drug_query(drug_id) and only_need_ids:
        return _queryset_well_ids(dataset_id, drug_id, cell_line_id), \
               drug_id, cell_line_id

    # Filter by dataset
    if isinstance(dataset_id, Iterable):
        well_info_base = Well.objects.filter(
            plate__dataset_id__in=dataset_id
        )
    else:
        well_info_base = Well.objects.filter(
            plate__dataset_id=dataset_id
        )

    # Filter by cell line
    well_info_base = _add_int_or_list_filter(well_info_base,
                                             'cell_line_id',
                                             cell_line_id)

    if drug_id is not None:
        well_info_base = well_info_base.annotate(num_drugs=Count('welldrug'))

    # Filter control wells (these are fetched separately)
    well_info_base = well_info_base.annotate(total_dose=Sum(
        'welldrug__dose')).filter(total_dose__gt=0)

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
    queryset = queryset.annotate(max_dose=Coalesce(Max(
        'well__welldrug__dose'), 0)).filter(max_dose=0)

    return _add_int_or_list_filter(queryset, 'well__cell_line_id',
                                   cell_line_id)


def _dataframe_wellinfo(dataset_id, drug_id, cell_line_id,
                        use_dataset_names=False, for_export=False):
    well_info, drug_id, cell_line_id = _queryset_well_info(
        dataset_id, drug_id, cell_line_id)

    well_info = well_info.prefetch_related('welldrug_set',
                                           'welldrug_set__drug')
    well_info = well_info.select_related('cell_line', 'plate')
    if use_dataset_names:
        well_info = well_info.select_related('plate__dataset')

    df_doses = pd.DataFrame({'dose': tuple(d.dose for d in
                                       well.welldrug_set.all()),
                             'well_id':  well.id,
                             'well_num': well.well_num,
                             'cell_line': well.cell_line.name,
                             'drug': tuple(d.drug.name for d in
                                      well.welldrug_set.all()),
                             'plate_id': well.plate_id if not
                                      for_export else well.plate.name,
                             'dataset': dataset_id if (not isinstance(
                                 dataset_id, Iterable) and not
                                use_dataset_names)
                             else (well.plate.dataset.name if
                                   use_dataset_names else
                             well.plate.dataset_id)} for well in well_info)
    if not df_doses.empty:
        df_doses.set_index(keys=['dataset', 'drug', 'cell_line', 'dose'],
                           inplace=True)

    return df_doses


def df_doses_assays_controls(dataset, drug_id, cell_line_id, assay,
                             for_export=False):
    dataset_id = dataset.id

    well_info, drug_id, cell_line_id = _queryset_well_info(
        dataset_id, drug_id, cell_line_id)

    df_doses = _dataframe_wellinfo(dataset_id, drug_id, cell_line_id,
                                   for_export=for_export)

    if df_doses.isnull().values.all():
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

    ctrl_cols = ['assay',
                 'well__cell_line__name',
                 'well__plate__name' if
                    for_export else
                    'well__plate_id',
                 'well_id',
                 'timepoint',
                 'value']
    ctrl_rename_cols = ['assay',
                        'cell_line',
                        'plate',
                        'well_id',
                        'timepoint',
                        'value']
    ctrl_indexes = ['assay',
                    'cell_line',
                    'plate',
                    'well_id',
                    'timepoint']
    if for_export:
        ctrl_cols.append('well__well_num')
        ctrl_rename_cols.append('well_num')

    df_controls = queryset_to_dataframe(controls,
                                        columns=ctrl_cols,
                                        rename_columns=ctrl_rename_cols,
                                        index=ctrl_indexes)
    if df_controls.isnull().values.all():
        df_controls = None

    return HtsPandas(df_doses, df_vals, df_controls)


def is_multi_drug_query(drug_id):
    # If drug ID is None, we assume the dataset may contain drug combos
    return drug_id is None or (
        isinstance(drug_id, Iterable) and
        any(not isinstance(d, int) for d in drug_id)
    )


def df_dip_rates(dataset_id, drug_id, cell_line_id,
                 use_dataset_names=False):
    dip_stats = ('dip_rate', 'dip_fit_std_err')

    dataset_id_field = 'well__plate__dataset' + ('__name' if
                                                 use_dataset_names else '_id')

    well_info, drug_id, cell_line_id = _queryset_well_info(
        dataset_id, drug_id, cell_line_id, only_need_ids=True)

    if is_multi_drug_query(drug_id):
        # This query is complex, so we use list() to store the well_ids in
        # Python before passing it to the two queries that use it
        well_ids = list(well_info.values_list('id', flat=True).distinct())

        df_cl_dset = queryset_to_dataframe(
            WellStatistic.objects.filter(
                well_id__in=well_ids,
                stat_name__in=dip_stats,
            ),
            columns=('stat_name', 'value', 'well_id'),
            rename_columns=('stat_name', 'value', 'well_id')
        )

        df_stats = df_cl_dset.pivot_table(index='well_id', columns='stat_name',
                                          values='value')

        df_drugs = queryset_to_dataframe(
            WellDrug.objects.filter(well_id__in=well_ids).order_by('well_id',
                                                                   'order'),
            columns=('well_id', 'drug__name', 'dose', 'well__cell_line__name',
                     dataset_id_field),
            rename_columns=('well_id', 'drug', 'dose', 'cell_line', 'dataset'),
            index=('well_id', )
        )

        df_drugs = df_drugs.groupby('well_id').aggregate({
            'drug': lambda x: tuple(x),
            'dose': lambda x: tuple(x),
            'dataset': lambda x: x,
            'cell_line': lambda x: x
        })

        df_doses = pd.merge(df_stats, df_drugs, left_index=True, right_index=True)
        df_doses.reset_index(inplace=True)
        df_doses.set_index(['dataset', 'drug', 'cell_line', 'dose', 'well_id'],
                           inplace=True)
        df_doses.sort_index(inplace=True)
    else:
        # In the single drug case, we can do everything in a single query
        df_doses = queryset_to_dataframe(
            WellStatistic.objects.filter(
                well_id__in=well_info.values_list('well_id').distinct(),
                stat_name__in=dip_stats,
            ),
            columns=('stat_name', 'value', 'well__welldrug__dose', 'well_id',
                     'well__cell_line__name', 'well__welldrug__drug__name',
                     dataset_id_field),
            rename_columns=(
            'stat_name', 'value', 'dose', 'well_id', 'cell_line',
            'drug', 'dataset')
        )

        if df_doses.isnull().values.all():
            raise NoDataException()

        df_doses[['dose', 'drug']] = \
            df_doses.transform({'dose': lambda x: (x, ),
                                'drug': lambda x: (x, )})

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
