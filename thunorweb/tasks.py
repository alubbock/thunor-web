from .models import HTSDataset, WellMeasurement, WellStatistic, CellLine, \
    Drug, WellDrug, Well
from .pandas import df_doses_assays_controls, NoDataException
from thunor.dip import dip_rates, _choose_dip_assay
import itertools
import numpy as np
from django.db import transaction
from django.db.models import Count, F
from collections import defaultdict, Sequence
from django.core.cache import cache


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


def _get_remapping(ids, names):
    names = np.array(names)

    remapping = {}

    # Convert to title case
    names_title_case = np.array([x.title() for x in names])

    for name in names_title_case:
        positions = np.where(names_title_case == name)[0]
        drug_name_matches = names[positions]
        try:
            true_pos = positions[np.where(drug_name_matches == name)[
                0][0]]
        except IndexError:
            true_pos = positions[0]
        for pos in positions:
            if pos != true_pos:
                remapping[ids[pos]] = ids[true_pos]

    return remapping


def reconcile_cell_line_and_drug_duplicates():
    cell_line_ids, cell_line_names = zip(
        *CellLine.objects.all().order_by('id').values_list('id', 'name'))

    cell_line_remapping = _get_remapping(cell_line_ids, cell_line_names)

    drug_ids, drug_names = zip(
        *Drug.objects.all().order_by('id').values_list('id', 'name'))

    drug_remapping = _get_remapping(drug_ids, drug_names)

    with transaction.atomic():
        for old_id, new_id in drug_remapping.items():
            WellDrug.objects.filter(drug_id=old_id).update(drug_id=new_id)

        delete_res = Drug.objects.filter(id__in=drug_remapping.keys()).delete()
        if delete_res[1].get('thunorweb.WellDrug', 0) != 0:
            raise Exception('Integrity error, database rolled back for '
                            'safety. You will need to rerun the query.')

        for old_id, new_id in cell_line_remapping.items():
            Well.objects.filter(cell_line=old_id).update(cell_line=new_id)

        delete_res = CellLine.objects.filter(
            id__in=cell_line_remapping.keys()).delete()
        if delete_res[1].get('thunorweb.Well', 0) != 0:
            raise Exception('Integrity error, database rolled back for '
                            'safety. You will need to rerun the query.')


def dataset_groupings(datasets, regenerate_cache=False):
    if isinstance(datasets, Sequence) and len(datasets) == 1:
        datasets = datasets[0]

    if isinstance(datasets, HTSDataset):
        return _dataset_groupings(_dataset_groupings(
            datasets, regenerate_cache=regenerate_cache))

    # Multi dataset
    groups = [_dataset_groupings(d, regenerate_cache=regenerate_cache)
              for d in datasets]
    grp_it = range(len(groups))

    cell_lines = _combine_id_name_dicts(groups[i]['cellLines'] for i in grp_it)
    drugs = _combine_id_name_dicts(groups[i]['drugs'] for i in grp_it)
    assays = _combine_id_name_dicts(groups[i]['assays'] for i in grp_it)

    single_timepoint = False
    timepoints = list(set(groups[i]['singleTimepoint'] for i in grp_it))
    if len(timepoints) == 1 and timepoints[0] is not False:
        single_timepoint = timepoints[0]

    return {
        'datasets': list(groups[i]['datasets'][0] for i in grp_it),
        'cellLines': cell_lines,
        'drugs': drugs,
        'assays': assays,
        'singleTimepoint': single_timepoint
    }


def _combine_id_name_dicts(dicts):
    combined = {}
    for d in dicts:
        combined.update({e['id']: e for e in d})

    return sorted(combined.values(), key=lambda e: e['name'])


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

    cell_line_dict = [{'id': cl['cell_line_id'],
                       'name': cl['cell_line__name']}
                      for cl in cell_lines]

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
    drug_list = sorted(drug_list, key=lambda d: d['name'])

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
        'assays': assays,
        'singleTimepoint': timepoints[0] if len(timepoints) == 1 else False
    }

    cache.set(cache_key, groupings_dict)

    return groupings_dict
