import pandas as pd
from .models import Well, WellDrug, WellMeasurement
import functools
from django.db.models import Q, Count
import operator
import numpy as np
from datetime import timedelta


TIME_0 = timedelta(0)


class NoDataException(Exception):
    pass


def df_single_cl_drug(dataset_id, cell_line_id, drug_id, assay, control=None,
                      log2y=False, normalize_as='dr',
                      aggregates=(np.mean, np.min, np.max)):
    """

    Parameters
    ----------
    dataset_id
    cell_line_id
    drug_id
    assay
    control
    log2y
    normalize_as : str
        'dr' to normalize as a dose/response curve (divide by the control at
        the same time point)
        'tc' to normalize as a time course (divide by the control at t=0)
    aggregates

    Returns
    -------

    """
    # TODO: Check drug/cell line combos split across more than one plate
    drug_ids = [drug_id]
    if control is not None:
        drug_ids.append(control)

    well_ids = list(WellDrug.objects.filter(
        drug_id__in=drug_ids,
        well__plate__dataset_id=dataset_id,
    ).values('well_id').annotate(num_drugs=Count('well_id')).filter(
        num_drugs=1).distinct().values_list('well_id', flat=True))

    if not well_ids:
        raise NoDataException()

    # Load cell lines and drugs (to find applicable wells and names)
    cell_lines = list(Well.objects.filter(
                    id__in=well_ids,
                    cell_line_id=cell_line_id).select_related(
        'cell_line').order_by('plate', 'well_num'))

    if not cell_lines:
        raise NoDataException()

    well_ids = set([cl.id for cl in cell_lines])

    cell_line_name = cell_lines[0].cell_line.name
    cell_line_df = pd.DataFrame([[cl.plate_id, cl.well_num] for
                                 cl in cell_lines], columns=('plate',
                                                             'well'))

    drugs = list(WellDrug.objects.filter(well_id__in=well_ids,
                                         drug__in=drug_ids).select_related(
        'drug').order_by('drug', 'well__plate_id', 'well__well_num'))

    drug_name = None
    control_name = None
    for dr in drugs:
        if dr.drug_id == drug_id:
            drug_name = dr.drug.name
        if dr.drug_id == control:
            control_name = dr.drug.name
        if control_name and drug_name:
            break

    drug_df = pd.DataFrame([[dr.well.plate_id,
                             dr.well.well_num,
                             dr.drug_id,
                             dr.dose] for
                             dr in drugs], columns=('plate',
                                                    'well',
                                                    'drug',
                                                    'dose'))

    # Combine drugs and cell lines to get the relevant plates and wells
    drug_cl_intersection = pd.merge(cell_line_df, drug_df, how='inner',
                                    on=('plate', 'well'))

    # Get the assay values
    vals = pd.DataFrame(list(WellMeasurement.objects.filter(
        well_id__in=well_ids, assay=assay).order_by(
        'timepoint', 'well__plate_id', 'well__well_num').\
        values_list('timepoint', 'well__plate_id', 'well__well_num', 'value')),
                        columns=('time', 'plate', 'well', 'value'))

    df_all = pd.merge(vals, drug_cl_intersection, how='outer',
                      on=['plate', 'well'])
    df_all.set_index(['drug', 'plate', 'time', 'dose'], inplace=True)

    main_df = df_all.loc[drug_id] if control else df_all
    main_vals = main_df['value']

    if control is not None:
        if normalize_as == 'dr':
            ctrl_means = df_all.loc[control].groupby(
                level=['plate', 'time']).mean()['value']
        elif normalize_as == 'tc':
            ctrl_means = df_all.loc[(df_all.index.get_level_values('drug') ==
                                    control) &
                                    (df_all.index.get_level_values('time') ==
                                    TIME_0)].\
                groupby(level='plate').mean()['value']
        else:
            raise Exception('Invalid normalize_as value: ' + normalize_as)

        for row in range(main_vals.shape[0]):
            # idx = [plate, time, dose]
            idx = main_vals.index.values[row]

            if normalize_as == 'dr':
                main_vals.set_value(row,
                                    main_vals.iloc[row] /
                                    ctrl_means.loc[idx[0], idx[1]],
                                    takeable=True)
            elif normalize_as == 'tc':
                main_vals.set_value(row,
                                    main_vals.iloc[row] /
                                    ctrl_means.loc[idx[0]], takeable=True)

    if log2y:
        main_vals = np.log2(main_vals)

    # Calculate summary statistics
    df = main_vals.groupby(level=('time', 'dose')).agg(aggregates)

    return {'df': df, 'log2y': log2y,
            'assay_name': assay,
            'control_name': control_name,
            'drug_name': drug_name,
            'cell_line_name': cell_line_name}
