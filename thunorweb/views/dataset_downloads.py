from django.shortcuts import Http404
from django.http import HttpResponse
from django.utils import timezone
from thunorweb.models import HTSDataset, HTSDatasetFile, Well, CurveFitSet
from thunor.curve_fit import fit_params_from_base
from thunor.io import write_hdf, _unstack_doses
from thunorweb.pandas import df_doses_assays_controls, df_curve_fits, \
    NoDataException, df_dip_rates
import numpy as np
import pandas as pd
from django.conf import settings
import os
from thunorweb.serve_file import serve_file
from thunorweb.views.datasets import license_accepted, LICENSE_UNSIGNED
from django.views.decorators.clickjacking import xframe_options_sameorigin
from thunorweb.views import login_required_unless_public, _assert_has_perm


def _cached_file(dataset, file_type, protocol):
    try:
        file = HTSDatasetFile.objects.get(
            dataset_id=dataset.id,
            file_type=file_type,
            file_type_protocol=protocol
        )
    except HTSDatasetFile.DoesNotExist:
        return None

    if file.creation_date < dataset.modified_date:
        # File needs updating
        return None

    return file


def _plain_response(response_text):
    response = HttpResponse(response_text, content_type='text/plain')
    response['Content-Disposition'] = \
        'attachment; filename="download_failed.txt"'
    response['Set-Cookie'] = 'fileDownload=true; path=/'
    return response


@login_required_unless_public
@xframe_options_sameorigin
def download_fit_params(request, dataset_id, stat_type):
    file_type = 'fit_params_{}_tsv'.format(stat_type)
    file_name = 'fit_params_{}_{}.tsv'.format(stat_type, dataset_id)
    file_type_protocol = 1
    param_names = {
        'dip': ('aa', 'aa_obs', 'emax', 'emax_rel', 'emax_obs', 'emax_obs_rel',
                'einf', 'ec50', 'ic50', 'hill'),
        'viability': ('aa', 'aa_obs', 'emax', 'emax_obs', 'einf', 'ec50',
                      'ic50', 'hill')
    }

    try:
        dataset = HTSDataset.objects.get(pk=dataset_id, deleted_date=None)
    except (HTSDataset.DoesNotExist, ValueError):
        return _plain_response('This dataset does not exist, or you do not '
                               'have permission to access it.')

    _assert_has_perm(request, dataset, 'download_data')
    if not license_accepted(request, dataset):
        return _plain_response('You must accept the dataset license to '
                               'download this file')

    mod_date = timezone.now()
    file = _cached_file(dataset, file_type, file_type_protocol)

    # Additional cache invalidation: curve fits were generated after the
    # cached file
    if file:
        if file.creation_date < CurveFitSet.objects.get(
                    dataset_id=dataset_id, stat_type=stat_type
                ).calculation_end:
            file = None

    if file:
        full_path = file.file.name
    else:
        try:
            # Fetch the DIP rates from the DB
            base_params = df_curve_fits(dataset.id, stat_type,
                                        drug_ids=None, cell_line_ids=None)
        except NoDataException:
            return _plain_response(
                'The requested parameter set does not exist for the '
                'specified dataset'
            )

        # Fit Hill curves and compute parameters
        fp = fit_params_from_base(
            base_params,
            custom_ic_concentrations={50},
            custom_ec_concentrations={50},
            include_auc=False,
            include_aa=True,
            include_hill=True,
            include_emax=True,
            include_einf=True,
            include_response_values=False
        )
        fp.reset_index('dataset_id', drop=True, inplace=True)
        # Remove -ve AA values
        fp.loc[fp['aa'] < 0.0, 'aa'] = np.nan

        # Filter for the default list of parameters only
        fp = fp.filter(items=param_names[stat_type])

        full_path = os.path.join(settings.DOWNLOADS_ROOT, file_name)

        fp.to_csv(full_path, sep='\t')

        df, created = HTSDatasetFile.objects.get_or_create(
            dataset=dataset,
            file_type=file_type,
            defaults={
                'file_type_protocol': file_type_protocol,
                'file': full_path
            }
        )
        if not created:
            df.file_type_protocol = file_type_protocol
            df.file = full_path
            df.creation_date = mod_date
            df.save()

    output_filename = '{}_{}_params.tsv'.format(dataset.name, stat_type)

    return serve_file(request, full_path, rename_to=output_filename,
                      content_type='text/tab-separated-values')


def _generate_dataset_hdf5(dataset, regenerate_cache=False):
    file_name = 'dataset_{}.h5'.format(dataset.id)
    file_type = 'dataset_hdf5'
    file_type_protocol = 1

    mod_date = timezone.now()
    file = _cached_file(dataset, file_type, file_type_protocol)

    if file and not regenerate_cache:
        full_path = file.file.name
    else:
        df_data = df_doses_assays_controls(
            dataset=dataset,
            drug_id=None,
            cell_line_id=None,
            assay=None,
            for_export=True
        )

        full_path = os.path.join(settings.DOWNLOADS_ROOT, file_name)
        write_hdf(df_data, full_path)
        df, created = HTSDatasetFile.objects.get_or_create(
            dataset=dataset,
            file_type=file_type,
            defaults={
                'file_type_protocol': file_type_protocol,
                'file': full_path
            }
        )
        if not created:
            df.file_type_protocol = file_type_protocol
            df.file = full_path
            df.creation_date = mod_date
            df.save()

    return full_path


@login_required_unless_public
@xframe_options_sameorigin
def download_dataset_hdf5(request, dataset_id):
    try:
        dataset = HTSDataset.objects.get(pk=dataset_id, deleted_date=None)
    except HTSDataset.DoesNotExist:
        raise Http404()

    _assert_has_perm(request, dataset, 'download_data')
    if not license_accepted(request, dataset):
        return _plain_response('You must accept the dataset license to '
                               'download this file')

    try:
        full_path = _generate_dataset_hdf5(dataset)
    except NoDataException:
        return _plain_response('No data found for this request')

    output_filename = '{}.h5'.format(dataset.name)

    return serve_file(request, full_path, rename_to=output_filename,
                      content_type='application/x-hdf5')


def _generate_dip_rates(dataset, regenerate_cache=False):
    file_name = 'dip_rates_{}.h5'.format(dataset.id)
    file_type = 'dip_rates'
    file_type_protocol = 1

    mod_date = timezone.now()
    file = _cached_file(dataset, file_type, file_type_protocol)

    if file and not regenerate_cache:
        full_path = file.file.name
    else:
        ctrl, expt = df_dip_rates(dataset, cell_line_id=None, drug_id=None)

        expt = expt.reset_index()
        n_drugs = expt['drug'].apply(len).max()
        expt = _unstack_doses(expt).reset_index()

        wells = Well.objects.filter(plate__dataset_id=dataset.id
                                    ).select_related('plate')

        if ctrl is None:
            df_data = expt
        else:
            ctrl = ctrl.reset_index()
            df_data = pd.concat([ctrl, expt], ignore_index=True, sort=False)

        df_data.drop(columns=['plate', 'dataset'], inplace=True)

        well_df = pd.DataFrame({
            'well_id': well.id,
            'plate': well.plate.name,
            'well_num': well.well_num,
            'well': well.plate.well_id_to_name(well.well_num)
        } for well in wells)

        df_data = df_data.merge(well_df, on='well_id')

        df_data.rename(columns={f'dose{n+1}': f'drug{n+1}.conc'
                                for n in range(n_drugs)},
                       inplace=True)
        df_data.rename(columns={'cell_line': 'cell.line'}, inplace=True)

        df_data.sort_values(['plate', 'well_num'], inplace=True)

        columns = ['plate', 'well', 'cell.line'] + \
            [f'drug{n+1}' for n in range(n_drugs)] + \
            [f'drug{n+1}.conc' for n in range(n_drugs)] + \
            ['dip_rate', 'dip_fit_std_err']
        df_data = df_data[columns]

        full_path = os.path.join(settings.DOWNLOADS_ROOT, file_name)
        df_data.to_csv(full_path, sep='\t', index=False)
        df, created = HTSDatasetFile.objects.get_or_create(
            dataset=dataset,
            file_type=file_type,
            defaults={
                'file_type_protocol': file_type_protocol,
                'file': full_path
            }
        )
        if not created:
            df.file_type_protocol = file_type_protocol
            df.file = full_path
            df.creation_date = mod_date
            df.save()

    return full_path


@login_required_unless_public
@xframe_options_sameorigin
def download_dip_rates(request, dataset_id):
    try:
        dataset = HTSDataset.objects.get(pk=dataset_id, deleted_date=None)
    except HTSDataset.DoesNotExist:
        raise Http404()

    _assert_has_perm(request, dataset, 'download_data')
    if not license_accepted(request, dataset):
        return _plain_response('You must accept the dataset license to '
                               'download this file')

    try:
        full_path = _generate_dip_rates(dataset)
    except NoDataException:
        return _plain_response('No data found for this request')

    output_filename = '{}_dip_rates.tsv'.format(dataset.name)

    return serve_file(request, full_path, rename_to=output_filename,
                      content_type='text/tab-separated-values')
