from .models import HTSDataset, WellMeasurement, WellStatistic, CellLine, \
    Drug, WellDrug, Well, CurveFit, CurveFitSet
from .pandas import df_doses_assays_controls, NoDataException, df_dip_rates
from thunor.dip import dip_rates, _choose_dip_assay
from thunor.curve_fit import fit_params_minimal
import itertools
from django.db import transaction
from django.db.models import Count, F
from collections import defaultdict, Sequence
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
import pickle
from thunor.curve_fit import HillCurveLL3u, HillCurveLL4
from thunor.viability import viability


# Increment these versions to indicate a change in calculation protocols
DIP_PROTOCOL_VER = 1
VIABILITY_PROTOCOL_VER = 1

DEFAULT_VIABILITY_TIME_HRS = 72
SECONDS_IN_HOUR = 3600

# Maximum number of cominbations to process at once
MAX_COMBINATIONS_AT_ONCE = 10000


def precalculate_dip_rates(dataset_or_id):
    if isinstance(dataset_or_id, HTSDataset):
        dataset = dataset_or_id
    elif isinstance(dataset_or_id, int):
        dataset = HTSDataset.objects.get(pk=dataset_or_id)
    else:
        raise ValueError('Argument must be an HTSDataset or an integer '
                         'primary key')

    # Auto-select DIP rate assay
    assays_times = WellMeasurement.objects.filter(
        well__plate__dataset_id=dataset.id
    ).values_list('assay', 'timepoint').distinct()

    assays = set(at[0] for at in assays_times)

    dip_assay = _choose_dip_assay(assays)

    if dip_assay is None:
        return

    times = set(at[1] for at in assays_times if at[0] == dip_assay)
    if len(times) < 2:
        return

    try:
        df_data = df_doses_assays_controls(
            dataset=dataset,
            drug_id=None,
            cell_line_id=None,
            assay=dip_assay
        )
    except NoDataException:
        return

    ctrl_dip_data, expt_dip_data = dip_rates(df_data)

    if expt_dip_data.empty:
        return

    expt_dip_data.reset_index('well_id', inplace=True)

    well_stats_to_create = [
        (WellStatistic(
            well_id=well_stat.well_id,
            stat_name='dip_rate',
            value=well_stat.dip_rate
        ),
         WellStatistic(
             well_id=well_stat.well_id,
             stat_name='dip_fit_std_err',
             value=well_stat.dip_fit_std_err
         ))
        for well_stat in
        expt_dip_data.itertuples(index=False)
    ]

    if ctrl_dip_data is not None:
        ctrl_dip_data.reset_index('well_id', inplace=True)
        well_stats_to_create.extend([
            (WellStatistic(
                well_id=well_stat.well_id,
                stat_name='dip_rate',
                value=well_stat.dip_rate
            ),
             WellStatistic(
                well_id=well_stat.well_id,
                stat_name='dip_fit_std_err',
                value=well_stat.dip_fit_std_err
            ))
            for well_stat in
            ctrl_dip_data.itertuples(index=False)
        ])

    # Delete any existing WellStatistics
    WellStatistic.objects.filter(
        well__plate__dataset=dataset.id,
        stat_name__in=['dip_rate', 'dip_fit_std_err']
    ).delete()

    WellStatistic.objects.bulk_create(
        itertools.chain.from_iterable(well_stats_to_create)
    )


@transaction.atomic
def precalculate_dip_curves(dataset_or_id, verbose=False,
                            delete_previous=True):
    if isinstance(dataset_or_id, HTSDataset):
        dataset = dataset_or_id
    elif isinstance(dataset_or_id, int):
        dataset = HTSDataset.objects.get(pk=dataset_or_id)
    else:
        raise ValueError('Argument must be an HTSDataset or an integer '
                         'primary key')

    groupings = dataset_groupings(dataset)
    if groupings['singleTimepoint'] is not False:
        return

    cell_line_ids = Well.objects.filter(
        plate__dataset=dataset,
        cell_line__isnull=False
    ).values_list('cell_line_id', flat=True).distinct()

    if not cell_line_ids:
        return

    cell_lines = {cl.name: cl for cl in CellLine.objects.all()}
    drugs = {dr.name: dr for dr in Drug.objects.all()}

    if len(cell_lines) * len(drugs) < MAX_COMBINATIONS_AT_ONCE:
        cell_line_ids = [None]

    # Delete previous if required
    if delete_previous:
        CurveFitSet.objects.filter(dataset=dataset, stat_type='dip').delete()

    cfs = CurveFitSet.objects.create(
        dataset=dataset,
        stat_type='dip',
        fit_protocol=DIP_PROTOCOL_VER,
        viability_time=timedelta(0),
        calculation_start=timezone.now()
    )

    for i, cl_id in enumerate(cell_line_ids):
        if verbose:
            print('Cell line {} of {} (ID: {})...'.format(
                i + 1, len(cell_line_ids), cl_id))
        try:
            # Fetch the DIP rates from the DB
            ctrl_dip_data, expt_dip_data = df_dip_rates(
                dataset_id=dataset.id,
                drug_id=None,
                cell_line_id=cl_id
            )
        except NoDataException:
            continue

        # Exclude combinations
        expt_dip_data = expt_dip_data[
            [len(d) == 1 for d in
             expt_dip_data.index.get_level_values('drug')]]

        if expt_dip_data.empty:
            continue

        # Fit Hill curves and compute parameters
        fp_data = fit_params_minimal(
            ctrl_dip_data, expt_dip_data,
            fit_cls=HillCurveLL4
        )

        fits = []

        for fp in fp_data.itertuples():
            fits.append(CurveFit(
                fit_set=cfs,
                cell_line=cell_lines[fp.Index[1]],
                drug=drugs[fp.Index[2]],
                curve_fit_class=fp.fit_obj.__class__.__name__
                    if fp.fit_obj else None,
                fit_params=pickle.dumps(fp.fit_obj.popt if fp.fit_obj else
                                        None),
                min_dose=fp.min_dose_measured,
                max_dose=fp.max_dose_measured,
                emax_obs=fp.emax_obs
            ))

        CurveFit.objects.bulk_create(fits)

    cfs.calculation_end = timezone.now()
    cfs.save()


@transaction.atomic
def precalculate_viability(dataset_or_id, time_hrs=None, assay_name=None,
                           verbose=False, delete_previous=True):
    if isinstance(dataset_or_id, HTSDataset):
        dataset = dataset_or_id
    elif isinstance(dataset_or_id, int):
        dataset = HTSDataset.objects.get(pk=dataset_or_id)
    else:
        raise ValueError('Argument must be an HTSDataset or an integer '
                         'primary key')

    cell_line_ids = Well.objects.filter(
        plate__dataset=dataset,
        cell_line__isnull=False
    ).values_list('cell_line_id', flat=True).distinct()

    if not cell_line_ids:
        return

    cell_lines = {cl.name: cl for cl in CellLine.objects.all()}
    drugs = {dr.name: dr for dr in Drug.objects.all()}

    if len(cell_lines) * len(drugs) < MAX_COMBINATIONS_AT_ONCE:
        cell_line_ids = [None]

    if time_hrs is None:
        groupings = dataset_groupings(dataset)
        if groupings['singleTimepoint'] is not False:
            viability_time = groupings['singleTimepoint']
        else:
            viability_time = timedelta(hours=DEFAULT_VIABILITY_TIME_HRS)
    else:
        viability_time = timedelta(hours=time_hrs)

    time_hrs = viability_time.total_seconds() / SECONDS_IN_HOUR

    # Delete previous if required
    if delete_previous:
        CurveFitSet.objects.filter(dataset=dataset,
                                   stat_type='viability').delete()

    cfs = CurveFitSet.objects.create(
        dataset=dataset,
        stat_type='viability',
        viability_time=viability_time,
        fit_protocol=VIABILITY_PROTOCOL_VER,
        calculation_start=timezone.now()
    )

    for i, cl_id in enumerate(cell_line_ids):
        if verbose:
            print('Cell line {} of {} (ID: {})...'.format(
                i + 1, len(cell_line_ids), cl_id))
        try:
            df_data = df_doses_assays_controls(
                dataset,
                cell_line_id=cl_id,
                drug_id=None,
                assay=assay_name
            )
        except NoDataException:
            continue

        if df_data.controls is None:
            continue

        # Exclude combinations
        df_data = df_data.filter(drugs=[d for d in df_data.drugs if len(d)
                                        == 1])
        if df_data.doses.empty:
            continue

        via, _ = viability(df_data, time_hrs=time_hrs,
                           assay_name=assay_name, include_controls=False)

        fits = []

        fp_data = fit_params_minimal(
            ctrl_data=None,
            expt_data=via,
            fit_cls=HillCurveLL3u
        )

        for fp in fp_data.itertuples():
            fits.append(CurveFit(
                fit_set=cfs,
                cell_line=cell_lines[fp.Index[1]],
                drug=drugs[fp.Index[2]],
                curve_fit_class=fp.fit_obj.__class__.__name__
                    if fp.fit_obj else None,
                fit_params=pickle.dumps(fp.fit_obj.popt if fp.fit_obj else
                                        None),
                min_dose=fp.min_dose_measured,
                max_dose=fp.max_dose_measured,
                emax_obs=fp.emax_obs
            ))

        CurveFit.objects.bulk_create(fits)

    cfs.calculation_end = timezone.now()
    cfs.save()


def dataset_groupings(datasets, regenerate_cache=False):
    if isinstance(datasets, Sequence) and len(datasets) == 1:
        datasets = datasets[0]

    if isinstance(datasets, HTSDataset):
        return _dataset_groupings(
            datasets, regenerate_cache=regenerate_cache)

    # Multi dataset
    groups = [_dataset_groupings(d, regenerate_cache=regenerate_cache)
              for d in datasets]
    grp_it = range(len(groups))

    cell_lines = _combine_id_name_dicts(groups[i]['cellLines'] for i in grp_it)
    drugs = _combine_id_name_dicts(groups[i]['drugs'] for i in grp_it)

    single_timepoint = False
    timepoints = list(set(groups[i]['singleTimepoint'] for i in grp_it))
    if len(timepoints) == 1 and timepoints[0] is not False:
        single_timepoint = timepoints[0]

    return {
        'datasets': list(groups[i]['datasets'][0] for i in grp_it),
        'cellLines': cell_lines,
        'drugs': drugs,
        'assays': [groups[i]['assays'][0] for i in grp_it],
        'dipAssay': [groups[i]['dipAssay'] for i in grp_it],
        'singleTimepoint': single_timepoint
    }


def _combine_id_name_dicts(dicts):
    dicts = list(dicts)
    combined = {k['id']: k for k in dicts[0]}
    for d in dicts[1:]:
        d_ids = set(k['id'] for k in d)
        for k in combined.keys() - d_ids:
            del combined[k]

    try:
        return sorted(combined.values(), key=lambda e: e['name'])
    except TypeError:
        # Dataset contains single drugs and combinations, sort them separately
        return sorted((e for e in combined.values()
                       if not isinstance(e['name'], tuple)),
                      key=lambda e: e['name'].lower()) + \
               sorted((e for e in combined.values()
                       if isinstance(e['name'], tuple)),
                      key=lambda e: e['name'])


def _dataset_groupings(dataset, regenerate_cache=False):
    cache_key = 'dataset_{}_groupings'.format(dataset.id)

    if not regenerate_cache:
        cache_val = cache.get(cache_key)
        if cache_val is not None:
            return cache_val

    cell_lines = Well.objects.filter(
        cell_line__isnull=False,
        plate__dataset_id=dataset.id).values(
        'cell_line_id', 'cell_line__name'
    ).distinct()

    cell_line_dict = sorted(({'id': cl['cell_line_id'],
                             'name': cl['cell_line__name']}
                            for cl in cell_lines),
                            key=lambda cl: cl['name'].lower())

    assays_query = WellMeasurement.objects.filter(
        well__plate__dataset_id=dataset.id
    ).values('assay', 'timepoint').distinct()

    assays = set(a['assay'] for a in assays_query)
    assays = [{'id': a, 'name': a} for a in assays if a is not None]

    timepoints = list(set(a['timepoint'] for a in assays_query))

    # Get drug without combinations
    drug_objs = WellDrug.objects.filter(
        drug__isnull=False,
        dose__gt=0,
        well__plate__dataset_id=dataset.id,
    ).annotate(num_drugs=Count('well__welldrug')). \
        values('drug_id', 'drug__name', 'num_drugs').distinct()

    has_drug_combos = any(dr['num_drugs'] > 1 for dr in drug_objs)
    drug_list = [{'id': dr['drug_id'], 'name': dr['drug__name']} for dr in
                 drug_objs if dr['num_drugs'] == 1]
    drug_list = sorted(drug_list, key=lambda d: d['name'].lower())

    if has_drug_combos:
        # Get drugs with combinations... this is inefficient but works
        # for arbitrary numbers of drugs per well
        drug_objs_combos = WellDrug.objects.filter(
            drug__isnull=False,
            dose__isnull=False,
            well__plate__dataset_id=dataset.id
        ).annotate(drug2_id=F('well__welldrug__drug_id')
                   ).exclude(drug_id=F('drug2_id')).values(
            'well_id', 'drug_id', 'drug__name') \
            .distinct()

        drug_well_combos = defaultdict(set)
        for d in drug_objs_combos:
            drug_well_combos[d['well_id']].add((d['drug_id'],
                                                d['drug__name']))

        drug_combos = set(frozenset(d) for d in drug_well_combos.values())

        for dc in drug_combos:
            drug_ids, drug_names = zip(*sorted(dc, key=lambda d: d[1]))
            drug_list.append({'id': drug_ids, 'name': drug_names})

    groupings_dict = {
        'datasets': [{'id': dataset.id, 'name': dataset.name}],
        'cellLines': cell_line_dict,
        'drugs': drug_list,
        'assays': [assays],
        'dipAssay': _choose_dip_assay(assays),
        'singleTimepoint': timepoints[0] if len(timepoints) == 1 else False
    }

    cache.set(cache_key, groupings_dict, timeout=None)

    return groupings_dict


def rename_dataset_in_cache(dataset_id, dataset_name):
    cache_key = 'dataset_{}_groupings'.format(dataset_id)
    groupings_dict = cache.get(cache_key)
    if groupings_dict is None:
        return

    groupings_dict['datasets'][0]['name'] = dataset_name

    cache.set(cache_key, groupings_dict, timeout=None)
