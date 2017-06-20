from .models import HTSDataset, WellStatistic
from .pandas import df_doses_assays_controls
from pydrc.dip import dip_rates
import itertools


def precalculate_dip_rates(dataset_or_id):
    if isinstance(dataset_or_id, HTSDataset):
        dataset = dataset_or_id
    elif isinstance(dataset_or_id, int):
        dataset = HTSDataset.objects.get(pk=dataset_or_id)
    else:
        raise ValueError('Argument must be an HTSDataset or an integer '
                         'primary key')
    df_data = df_doses_assays_controls(
        dataset=dataset,
        drug_id=None,
        cell_line_id=None,
        assay=dataset.dip_assay
    )

    ctrl_dip_data, expt_dip_data = dip_rates(df_data)

    well_stats_to_create = [
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
    ]

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
        expt_dip_data.itertuples(index=False)
    ])

    # Delete any existing WellStatistics
    WellStatistic.objects.filter(
        well__plate__dataset=dataset.id,
        stat_name__in=['dip_rate', 'dip_fit_std_err']
    ).delete()

    WellStatistic.objects.bulk_create(
        itertools.chain.from_iterable(well_stats_to_create)
    )
