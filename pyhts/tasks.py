from .models import HTSDataset, WellStatistic, CellLine, Drug, WellDrug, Well
from .pandas import df_doses_assays_controls, NoDataException
from pydrc.dip import dip_rates
import itertools
import numpy as np
from django.db import transaction


def precalculate_dip_rates(dataset_or_id):
    if isinstance(dataset_or_id, HTSDataset):
        dataset = dataset_or_id
    elif isinstance(dataset_or_id, int):
        dataset = HTSDataset.objects.get(pk=dataset_or_id)
    else:
        raise ValueError('Argument must be an HTSDataset or an integer '
                         'primary key')
    try:
        df_data = df_doses_assays_controls(
            dataset=dataset,
            drug_id=None,
            cell_line_id=None,
            assay=dataset.dip_assay
        )
    except NoDataException:
        return

    ctrl_dip_data, expt_dip_data = dip_rates(df_data)

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
        well_stats_to_create.extend([
            (WellStatistic(
                well_id=well_stat.Index[1],
                stat_name='dip_rate',
                value=well_stat.dip_rate
            ),
             WellStatistic(
                well_id=well_stat.Index[1],
                stat_name='dip_fit_std_err',
                value=well_stat.dip_fit_std_err
            ))
            for well_stat in
            ctrl_dip_data.itertuples()
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
        if delete_res[1].get('pyhts.WellDrug', 0) != 0:
            raise Exception('Integrity error, database rolled back for '
                            'safety. You will need to rerun the query.')

        for old_id, new_id in cell_line_remapping.items():
            Well.objects.filter(cell_line=old_id).update(cell_line=new_id)

        delete_res = CellLine.objects.filter(
            id__in=cell_line_remapping.keys()).delete()
        if delete_res[1].get('pyhts.Well', 0) != 0:
            raise Exception('Integrity error, database rolled back for '
                            'safety. You will need to rerun the query.')