import pandas as pd
from .models import WellCellLine, WellDrug, WellMeasurement
import functools
from django.db.models import Q
import operator


def df_dose_response(dataset_id, cell_line_id, drug_id, assay,
                        control=None):
    # TODO: Handle drug/cell line combos split across more than one plate
    cell_lines = list(WellCellLine.objects.filter(
                    plate__dataset_id=dataset_id,
                    cell_line_id=cell_line_id).select_related(
        'cell_line').order_by('plate', 'well'))

    cell_line_name = cell_lines[0].cell_line.name
    cell_line_df = pd.DataFrame([[cl.plate_id, cl.well] for
                                 cl in cell_lines], columns=('plate',
                                                             'well'))

    drugs = list(WellDrug.objects.filter(
        plate__dataset_id=dataset_id, drug=drug_id).select_related(
        'drug').order_by('plate', 'well'))

    drug_name = drugs[0].drug.name
    drug_df = pd.DataFrame([[dr.plate_id, dr.well, dr.dose] for
                             dr in drugs], columns=('plate',
                                                    'well',
                                                    'dose'))

    drug_cl_intersection = pd.merge(cell_line_df, drug_df, how='inner',
                                    on=('plate', 'well'))

    plate_well_list = functools.reduce(
        operator.or_,
        (Q(plate_id=row['plate'], well=row['well']) for i, row in
         drug_cl_intersection.iterrows())
    )

    vals = pd.DataFrame(list(WellMeasurement.objects.filter(
        plate__dataset_id=dataset_id, assay=assay).filter(plate_well_list)
                .order_by('timepoint', 'plate', 'well').values_list(
        'timepoint', 'plate_id', 'well', 'value')), columns=('time',
                                                             'plate',
                                                             'well',
                                                             'value'))

    df = pd.merge(vals, drug_cl_intersection, how='outer',
                  on=['plate', 'well']).set_index(['time', 'dose'])

    df = df.groupby(level=['time', 'dose']).mean()

    if control is not None:
        raise NotImplementedError()

    return {'df': df, 'drug_name': drug_name, 'cell_line_name': cell_line_name}
