import pandas as pd
from .models import WellCellLine, WellDrug, WellMeasurement
import functools
from django.db.models import Q
import operator
import numpy as np


def df_dose_response(dataset_id, cell_line_id, drug_id, assay, control=None,
                     aggregates=(np.mean, np.min, np.max)):
    # TODO: Check drug/cell line combos split across more than one plate

    # Load cell lines and drugs (to find applicable wells and names)
    cell_lines = list(WellCellLine.objects.filter(
                    plate__dataset_id=dataset_id,
                    cell_line_id=cell_line_id).select_related(
        'cell_line').order_by('plate', 'well'))

    cell_line_name = cell_lines[0].cell_line.name
    cell_line_df = pd.DataFrame([[cl.plate_id, cl.well] for
                                 cl in cell_lines], columns=('plate',
                                                             'well'))

    cell_line_plates = set([cl.plate_id for cl in cell_lines])

    drug_ids = [drug_id]
    if control is not None:
        drug_ids.append(control)

    drugs = list(WellDrug.objects.filter(
        plate_id__in=cell_line_plates, drug__in=drug_ids).select_related(
        'drug').order_by('drug', 'plate', 'well'))

    drug_name = None
    for dr in drugs:
        if dr.drug_id == drug_id:
            drug_name = dr.drug.name
            break

    drug_df = pd.DataFrame([[dr.plate_id, dr.well, dr.drug_id, dr.dose] for
                             dr in drugs], columns=('plate',
                                                    'well',
                                                    'drug',
                                                    'dose'))

    # Combine drugs and cell lines to get the relevant plates and wells
    drug_cl_intersection = pd.merge(cell_line_df, drug_df, how='inner',
                                    on=('plate', 'well'))

    plate_well_list = functools.reduce(
        operator.or_,
        (Q(plate_id=row['plate'], well=row['well']) for i, row in
         drug_cl_intersection.iterrows())
    )

    # Get the assay values
    vals = pd.DataFrame(list(WellMeasurement.objects.filter(
        plate__dataset_id=dataset_id, assay=assay).filter(plate_well_list)
                .order_by('timepoint', 'plate', 'well').values_list(
        'timepoint', 'plate_id', 'well', 'value')), columns=('time',
                                                             'plate',
                                                             'well',
                                                             'value'))

    df_all = pd.merge(vals, drug_cl_intersection, how='outer',
                      on=['plate', 'well'])
    df_all.set_index(['drug', 'plate', 'time', 'dose'], inplace=True)

    main_df = df_all.loc[drug_id] if control else df_all
    main_vals = main_df['value']

    if control is not None:
        ctrl_means = df_all.loc[control].groupby(level=[0, 1]).mean()['value']

        for row in range(main_vals.shape[0]):
            idx = main_vals.index.values[row]
            main_vals.set_value(row,
                                main_vals.iloc[row] /
                                ctrl_means.loc[idx[0], idx[1]],
                                takeable=True)

    # Calculate summary statistics
    df = main_vals.groupby(level=('time', 'dose')).agg(aggregates)

    return {'df': df, 'drug_name': drug_name, 'cell_line_name':
            cell_line_name}
