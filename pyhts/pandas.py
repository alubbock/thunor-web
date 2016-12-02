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


def df_single_cl_drug(user_id, dataset_id, cell_line_id, drug_id, assay,
                      control=None,
                      log2y=False, normalize_as='dr',
                      aggregates=(np.mean, np.min, np.max)):
    """

    Parameters
    ----------
    user_id
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

    # Load cell lines and drugs (to find applicable wells and names)
    cell_lines = list(Well.objects.filter(
                    plate__dataset_id=dataset_id,
                    plate__dataset__owner_id=user_id,
                    cell_line_id=cell_line_id).annotate(
        num_drugs=Count('welldrug')).filter(
        num_drugs=1).select_related(
        'cell_line').order_by('plate', 'well_num'))

    if not cell_lines:
        raise NoDataException()

    well_ids = [cl.id for cl in cell_lines]

    cell_line_name = cell_lines[0].cell_line.name

    drugs = list(WellDrug.objects.filter(well_id__in=well_ids,
                                         drug=drug_id).select_related(
        'drug', 'well').order_by('well__plate_id', 'well__well_num'))

    if not drugs:
        raise NoDataException()

    drug_name = drugs[0].drug.name

    if control is not None:
        control_data = list(WellDrug.objects.filter(
            well_id__in=well_ids,
            well__plate_id__in=[dr.well.plate_id for dr in drugs],
            drug_id=control
        ).select_related('drug').order_by(
            'well__plate_id', 'well__well_num'))
        if not control_data:
            raise NoDataException()
        control_name = control_data[0].drug.name
        drugs.extend(control_data)
    else:
        control_name = None

    drug_cl_intersection = pd.DataFrame([[dr.well.plate_id,
                             dr.well.well_num,
                             dr.drug_id,
                             dr.dose] for
                             dr in drugs], columns=('plate',
                                                    'well',
                                                    'drug',
                                                    'dose'))

    # Get the assay values
    vals = pd.DataFrame(list(WellMeasurement.objects.filter(
        well_id__in=[dr.well_id for dr in drugs], assay=assay).order_by(
        'timepoint', 'well__plate_id', 'well__well_num').\
        values_list('timepoint', 'well__plate_id', 'well__well_num', 'value')),
                        columns=('time', 'plate', 'well', 'value'))

    df_all = pd.merge(vals, drug_cl_intersection, how='outer',
                      on=['plate', 'well'])
    df_all.set_index(['drug', 'plate', 'time', 'dose'], inplace=True)

    main_df = df_all.loc[drug_id] if control else df_all
    main_vals = main_df['value']

    if main_vals.shape[0] == 0:
        raise NoDataException

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

        if ctrl_means.shape[0] == 0:
            raise NoDataException

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
