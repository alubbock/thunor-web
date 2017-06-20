from .models import HTSDataset, WellStatistic
from .pandas import df_doses_assays_controls
from pydrc.dip import dip_rates
import itertools


def precalculate_dip_rates(dataset_id):
    dataset = HTSDataset.objects.get(pk=dataset_id)
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

    WellStatistic.objects.bulk_create(
        itertools.chain.from_iterable(well_stats_to_create)
    )
