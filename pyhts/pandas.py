import pandas as pd
from .models import Well, WellDrug, WellMeasurement
import functools
from django.db.models import Q, Count
import operator
import numpy as np
import scipy.stats
from datetime import timedelta


TIME_0 = timedelta(0)


class NoDataException(Exception):
    pass


def df_drug_unaggregated(dataset_id, drug_id, cell_line_id,
                         assay, control=None):
    well_info = WellDrug.objects.filter(
        well__plate__dataset_id=dataset_id).annotate(
        num_drugs=Count('well__welldrug')).filter(
        num_drugs=1).select_related('well', 'well__cell_line', 'drug')

    if drug_id:
        well_info = well_info.filter(drug_id=drug_id).order_by(
             'well__cell_line__name', 'dose', 'well__plate_id',
             'well__well_num')

    if cell_line_id:
        well_info = well_info.filter(
            well__cell_line_id=cell_line_id).order_by(
            'drug__name', 'dose', 'well__plate_id', 'well__well_num')

    if control == 'A1':
        well_info = well_info.exclude(well__well_num=0)
    elif control == 0:
        well_info = well_info.exclude(dose=0)

    df_doses = queryset_to_dataframe(
        well_info,
        columns=('dose', 'well_id', 'well__cell_line__name', 'drug__name'),
        rename_columns=('dose', 'well_id', 'cell_line', 'drug'),
        index=('drug__name', 'well__cell_line__name', 'dose'))

    timecourses = WellMeasurement.objects.filter(well_id__in=(
        well.well_id for well in well_info), assay=assay).order_by(
        'well_id', 'timepoint')

    df_vals = queryset_to_dataframe(timecourses,
                                    columns=('well_id', 'timepoint', 'value'),
                                    index=('well_id', 'timepoint'))

    df_controls = None
    if control is not None:
        controls = WellMeasurement.objects.filter(
            well__plate__dataset_id=dataset_id,
            assay=assay).select_related(
            'well').order_by('well__cell_line', 'timepoint')
        if control == 'A1':
            controls = controls.filter(well__well_num=0)
        elif control == 0:
            controls = WellMeasurement.objects.filter(
                well__welldrug__dose=0,
            ).annotate(
                num_drugs=Count('well__welldrug')).filter(
                num_drugs=1)
        else:
            raise NotImplementedError()

        if cell_line_id:
            controls = controls.filter(well__cell_line_id=cell_line_id)

        df_controls = queryset_to_dataframe(controls,
                                            columns=('well__cell_line__name',
                                                     'well__plate__id',
                                                     'timepoint', 'value'),
                                            rename_columns=('cell_line',
                                                            'plate',
                                                            'timepoint',
                                                            'value'),
                                            index=('well__cell_line__name',
                                                   'well__plate__id',
                                                   'timepoint'))

    return {'doses': df_doses,
            'assays': df_vals,
            'controls': df_controls}


def queryset_to_dataframe(queryset, columns, index=None, rename_columns=None):
    df = pd.DataFrame.from_records(
        (x for x in queryset.values_list(*columns)),
        # queryset.values(*columns),
        columns=columns,
        index=index
    )
    if rename_columns:
        if index:
            df.columns = [new for old, new in zip(columns, rename_columns)
                          if old not in index]
            df.index.names = [rename_columns[columns.index(nm)] for nm in
                              df.index.names]
        else:
            df.columns = rename_columns
    return df


def df_single_cl_drug(dataset_id, cell_line_id, drug_id, assay,
                      # control=None,
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
    # if control is not None:
    #     drug_ids.append(control)

    # This query isn't executed immediately - Django internally combines it
    # with the next query to get all the drug details in a single DB hit
    plate_id_query = WellDrug.objects.filter(
        well__plate__dataset_id=dataset_id,
        # well__plate__dataset__owner_id=user_id,
        well__cell_line=cell_line_id,
        drug_id=drug_id).annotate(num_drugs=Count(
        'well__welldrug')).filter(
        num_drugs=1
        ).values_list('well__plate_id', flat=True).distinct()

    # We need to filter for num_drugs=1 again because the drug might be present
    # in isolation and in combination on the same plate
    drugs = WellDrug.objects.filter(
        drug_id__in=drug_ids, well__cell_line=cell_line_id,
        well__plate__in=plate_id_query).annotate(num_drugs=Count(
        'well__welldrug')).filter(
        num_drugs=1
        ).select_related(
        'drug', 'well', 'well__cell_line').order_by(
        'well__plate_id', 'well__well_num')

    # drug_cl_intersection = pd.DataFrame.from_records([[dr.well.plate_id,
    #                          dr.well.well_num,
    #                          dr.drug_id,
    #                          dr.dose] for
    #                          dr in drugs], columns=('plate',
    #                                                 'well',
    #                                                 'drug',
    #                                                 'dose'))

    drug_cl_intersection = queryset_to_dataframe(
        drugs,
        columns=('well__plate_id', 'well__well_num', 'drug_id', 'dose'),
        rename_columns=('plate', 'well', 'drug', 'dose')
    )

    if not drugs:
        raise NoDataException()

    cell_line_name = drugs[0].well.cell_line.name
    drug_name = None
    # control_name = None
    for dr in drugs:
        if dr.drug_id == drug_id:
            drug_name = dr.drug.name
        # if dr.drug_id == control:
        #     control_name = dr.drug.name
        # if drug_name is not None and control_name is not None:
        #     break

    # if control and control_name is None:
    #     raise NoDataException()

    # Get the assay values
    # vals = pd.DataFrame(list(WellMeasurement.objects.filter(
    #     well_id__in=[dr.well_id for dr in drugs], assay=assay).order_by(
    #     'timepoint', 'well__plate_id', 'well__well_num').\
    #     values_list('timepoint', 'well__plate_id', 'well__well_num', 'value')),
    #                     columns=('time', 'plate', 'well', 'value'))
    vals = queryset_to_dataframe(WellMeasurement.objects.filter(
        well_id__in=[dr.well_id for dr in drugs], assay=assay).order_by(
        'timepoint', 'well__plate_id', 'well__well_num'),
            columns=('timepoint', 'well__plate_id', 'well__well_num', 'value'),
            rename_columns=('time', 'plate', 'well', 'value')
    )

    df_all = pd.merge(vals, drug_cl_intersection, how='outer',
                      on=['plate', 'well'], sort=False)
    df_all.set_index(['drug', 'plate', 'time', 'dose'], inplace=True)
    df_all.sortlevel(inplace=True)

    # main_df = df_all.loc[drug_id] if control else df_all
    main_df = df_all
    main_vals = main_df['value']

    if main_vals.shape[0] == 0:
        raise NoDataException

    t0_extrapolated = False
    # if control is not None:
    #     if normalize_as == 'dr':
    #         ctrl_means = df_all.loc[control].groupby(
    #             level=['plate', 'time']).mean()['value']
    #     elif normalize_as == 'tc':
    #         ctrl_means = df_all.loc[(df_all.index.get_level_values('drug') ==
    #                                 control) &
    #                                 (df_all.index.get_level_values('time') ==
    #                                 TIME_0)].\
    #             groupby(level='plate').mean()['value']
    #         if ctrl_means.shape[0] == 0:
    #             # No time zero; extrapolate using exp growth model
    #             t0_extrapolated = True
    #             ctrl_means = df_all.loc[
    #                 (df_all.index.get_level_values('drug') == control),
    #                 'value'].groupby(level=['plate']).agg(extrapolate_time0)
    #     else:
    #         raise Exception('Invalid normalize_as value: ' + normalize_as)
    #
    #     if ctrl_means.shape[0] == 0:
    #         raise NoDataException
    #
    #     for row in range(main_vals.shape[0]):
    #         # idx = [plate, time, dose]
    #         idx = main_vals.index.values[row]
    #
    #         if normalize_as == 'dr':
    #             main_vals.set_value(row,
    #                                 main_vals.iloc[row] /
    #                                 ctrl_means.loc[idx[0], idx[1]],
    #                                 takeable=True)
    #         elif normalize_as == 'tc':
    #             main_vals.set_value(row,
    #                                 main_vals.iloc[row] /
    #                                 ctrl_means.loc[idx[0]], takeable=True)

    if log2y:
        main_vals = np.log2(main_vals)

    # Calculate summary statistics
    df = main_vals.groupby(level=('time', 'dose')).agg(aggregates)

    return {'df': df, 'log2y': log2y,
            'assay_name': assay,
            # 'control_name': control_name,
            'drug_name': drug_name,
            'cell_line_name': cell_line_name,
            't0_extrapolated': t0_extrapolated}


def extrapolate_time0(dat):
    means = dat.groupby(level=['time']).mean()
    return 2**scipy.stats.linregress(
        [t.item() for t in means.index.values],
        np.log2(list(means))).intercept
