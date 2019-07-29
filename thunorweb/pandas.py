import pandas as pd
from .models import Well, WellDrug, WellMeasurement, WellStatistic, CurveFit
from django.db.models import Count, Max, Sum
from django.db.models.functions import Coalesce
from collections import Iterable
from thunor.io import HtsPandas
from datetime import timedelta
import pickle
import thunor.curve_fit


class NoDataException(Exception):
    pass


SECONDS_IN_HOUR = 3600
DIP_STATS = ('dip_rate', 'dip_fit_std_err')


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
                             'plate': well.plate_id if not
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
                             for_export=False, use_dataset_names=False):
    dataset_id_field = 'well__plate__dataset' + ('__name' if
                                                 use_dataset_names else '_id')

    if isinstance(dataset, Iterable):
        dataset_id = [d.id for d in dataset]
    else:
        dataset_id = dataset.id

    df_doses = _dataframe_wellinfo(dataset_id, drug_id, cell_line_id,
                                   for_export=for_export,
                                   use_dataset_names=use_dataset_names
                                   )

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

    if for_export:
        # Get all plates in the dataset
        if isinstance(dataset_id, Iterable):
            raise NotImplementedError()
        controls = WellMeasurement.objects.filter(
            well__plate__dataset_id=dataset_id)
    else:
        # Just get controls on the plates with expt data
        controls = WellMeasurement.objects.filter(
            well__plate_id__in=df_doses['plate'].unique())

    controls = controls.select_related('well').order_by(
        dataset_id_field, 'well__cell_line', 'timepoint')
    if assay is not None:
        controls = controls.filter(assay=assay)
    controls = _apply_control_filter(controls, cell_line_id)

    ctrl_cols = [dataset_id_field,
                 'assay',
                 'well__cell_line__name',
                 'well__plate__name' if
                    for_export else
                    'well__plate_id',
                 'well_id',
                 'timepoint',
                 'value']
    ctrl_rename_cols = ['dataset',
                        'assay',
                        'cell_line',
                        'plate',
                        'well_id',
                        'timepoint',
                        'value']
    ctrl_indexes = ['dataset',
                    'assay',
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
                stat_name__in=DIP_STATS,
            ),
            columns=('stat_name', 'value', 'well_id'),
            rename_columns=('stat_name', 'value', 'well_id')
        )

        if df_cl_dset.empty:
            raise NoDataException()

        df_stats = df_cl_dset.pivot_table(index='well_id', columns='stat_name',
                                          values='value')

        df_drugs = queryset_to_dataframe(
            WellDrug.objects.filter(well_id__in=well_ids).order_by('well_id',
                                                                   'order'),
            columns=('well_id', 'drug__name', 'dose', 'well__cell_line__name',
                     dataset_id_field, 'well__plate_id'),
            rename_columns=('well_id', 'drug', 'dose', 'cell_line',
                            'dataset', 'plate'),
            index=('well_id', )
        )

        df_drugs = df_drugs.groupby('well_id').aggregate({
            'drug': lambda x: tuple(x),
            'dose': lambda x: tuple(x),
            'dataset': lambda x: x.iloc[0],
            'cell_line': lambda x: x.iloc[0],
            'plate': lambda x: x.iloc[0]
        })

        df_doses = pd.merge(df_stats, df_drugs, left_index=True, right_index=True)
        df_doses.reset_index(inplace=True)
        df_doses.set_index(['dataset', 'drug', 'cell_line', 'dose',
                            'plate', 'well_id'],
                           inplace=True)
        df_doses.sort_index(inplace=True)
    else:
        # In the single drug case, we can do everything in a single query
        df_doses = queryset_to_dataframe(
            WellStatistic.objects.filter(
                well_id__in=well_info.values_list('well_id').distinct(),
                stat_name__in=DIP_STATS,
            ),
            columns=('stat_name', 'value', 'well__welldrug__dose', 'well_id',
                     'well__cell_line__name', 'well__welldrug__drug__name',
                     dataset_id_field, 'well__plate_id'),
            rename_columns=(
            'stat_name', 'value', 'dose', 'well_id', 'cell_line',
            'drug', 'dataset', 'plate')
        )

        if df_doses['value'].isnull().values.all():
            raise NoDataException()

        df_doses[['dose', 'drug']] = \
            df_doses.transform({'dose': lambda x: (x, ),
                                'drug': lambda x: (x, )})

        df_doses = df_doses.pivot_table(
            index=('dataset', 'drug', 'cell_line', 'dose', 'plate', 'well_id'),
            columns='stat_name', values=['value'])['value']

    plates = df_doses.index.levels[df_doses.index.names.index('plate')]
    df_controls = df_ctrl_dip_rates(dataset_id=None,
                                    plate_ids=plates,
                                    cell_line_id=cell_line_id,
                                    use_plate_ids=True,
                                    use_dataset_names=use_dataset_names)

    return df_controls, df_doses


def df_ctrl_dip_rates(dataset_id, plate_ids=None, cell_line_id=None,
                      use_plate_ids=False, use_dataset_names=True):
    controls = WellStatistic.objects.filter(stat_name__in=DIP_STATS)
    if plate_ids is not None and dataset_id is None:
        controls = controls.filter(well__plate_id__in=plate_ids)
    elif dataset_id is not None and plate_ids is None:
        controls = controls.filter(well__plate__dataset__id=dataset_id)
    else:
        raise ValueError('Must specify one of dataset_id or plate_ids')

    controls = _apply_control_filter(controls, cell_line_id)

    df_controls = queryset_to_dataframe(
        controls,
        columns=('well__plate__dataset__name' if use_dataset_names else
                 'well__plate__dataset_id',
                 'well__cell_line__name',
                 'well__plate_id' if use_plate_ids else 'well__plate__name',
                 'well_id',
                 'stat_name', 'value'),
        rename_columns=('dataset', 'cell_line', 'plate', 'well_id',
                        'stat_name', 'value')
    )

    if df_controls['value'].isnull().values.all():
        df_controls = None
    else:
        df_controls = df_controls.pivot_table(
            index=('dataset', 'cell_line', 'plate', 'well_id'),
            columns='stat_name', values=['value'])['value']

    return df_controls


def _row_to_curve_fit(row):
    class_name = row['curve_fit_class']

    if class_name is None:
        return None
    else:
        curve_class = getattr(thunor.curve_fit, class_name)

    return curve_class(pickle.loads(row['fit_params']))


def df_curve_fits(dataset_ids, stat_type,
                  drug_ids, cell_line_ids, viability_time=None):
    cf = CurveFit.objects.filter(
        fit_set__stat_type=stat_type,
        fit_set__dataset_id__in=[dataset_ids] if isinstance(dataset_ids,
                                                 int) else dataset_ids,
    ).select_related('drug', 'cell_line').order_by('fit_set__dataset_id',
                                                   'cell_line__name',
                                                   'drug__name')
    cols = ['fit_set__dataset__name', 'cell_line__name', 'drug__name',
            'curve_fit_class', 'fit_params', 'max_dose',
            'min_dose', 'emax_obs', 'aa_obs']
    if viability_time is None:
        cols += ['fit_set__viability_time']
    else:
        cf = cf.filter(fit_set__viability_time=timedelta(hours=viability_time))
    if drug_ids is not None:
        cf = cf.filter(drug_id__in=drug_ids)
    if cell_line_ids is not None:
        cf = cf.filter(cell_line_id__in=cell_line_ids)

    base_params = queryset_to_dataframe(
        cf,
        columns=cols
    )
    if base_params.empty:
        raise NoDataException()

    if viability_time is None:
        viability_times = base_params['fit_set__viability_time'].unique()
        assert len(viability_times) == 1
        if viability_times[0] is not None:
            viability_time = viability_times[0].astype(
                'timedelta64[h]').item().total_seconds() / SECONDS_IN_HOUR
        base_params.drop(columns='fit_set__viability_time', inplace=True)

    base_params['fit_obj'] = base_params.apply(_row_to_curve_fit, axis=1)
    base_params.drop(columns=['curve_fit_class', 'fit_params'], inplace=True)
    base_params.rename(columns={
        'fit_set__dataset__name': 'dataset_id',
        'cell_line__name': 'cell_line',
        'drug__name': 'drug',
        'min_dose': 'min_dose_measured',
        'max_dose': 'max_dose_measured'
    }, inplace=True)
    base_params.set_index(['dataset_id', 'cell_line', 'drug'], inplace=True)

    base_params._drmetric = stat_type
    if stat_type == 'viability':
        base_params._viability_time = viability_time
        base_params._viability_assay = 'default'

    return base_params


def queryset_to_dataframe(queryset, columns, index=None, rename_columns=None):
    return pd.DataFrame.from_records(
        queryset.values_list(*columns).iterator(),
        columns=rename_columns or columns,
        index=index
    )
