from django.shortcuts import Http404
from django.http import HttpResponse
from thunorweb.models import HTSDataset
from thunor.plots import PARAM_NAMES
from thunor.curve_fit import fit_params, DrugCombosNotImplementedError
from thunor.io import write_hdf
from thunorweb.pandas import df_doses_assays_controls, df_dip_rates, \
    NoDataException
import numpy as np
from django.conf import settings
import tempfile
from thunorweb.serve_file import serve_file
from django.views.decorators.clickjacking import xframe_options_sameorigin
from thunorweb.views import login_required_unless_public, _assert_has_perm


@login_required_unless_public
@xframe_options_sameorigin
def download_dip_fit_params(request, dataset_id):
    dataset_name = 'dataset'
    try:
        dataset_id = int(dataset_id)
        dataset = HTSDataset.objects.get(pk=dataset_id, deleted_date=None)
        dataset_name = dataset.name

        _assert_has_perm(request, dataset, 'download_data')

        # Fetch the DIP rates from the DB
        ctrl_dip_data, expt_dip_data = df_dip_rates(
            dataset_id=dataset_id,
            drug_id=None,
            cell_line_id=None
        )

        # Fit Hill curves and compute parameters
        fp = fit_params(
            ctrl_dip_data, expt_dip_data
        )
        fp.reset_index('dataset_id', drop=True, inplace=True)
        # Remove -ve AA values
        fp.loc[fp['aa'] < 0.0, 'aa'] = np.nan

        # Filter for the default list of parameters only
        fp = fp.filter(items=PARAM_NAMES.keys())

        response = HttpResponse(fp.to_csv(), content_type='text/csv')
    except NoDataException:
        response = HttpResponse('No data found for this request. This '
                                'drug/cell line/assay combination may not '
                                'exist.',
                                content_type='text/plain')
    except (HTSDataset.DoesNotExist, ValueError):
        response = HttpResponse('This dataset does not exist, or you do not '
                                'have permission to access it.',
                                content_type='text/plain')
    except DrugCombosNotImplementedError:
        response = HttpResponse('Parameter calculations for datasets with '
                                'drug combinations is not yet implemented.',
                                content_type='text/plain')

    response['Content-Disposition'] = \
        'attachment; filename="{}_params.csv"'.format(dataset_name)
    response['Set-Cookie'] = 'fileDownload=true; path=/'
    return response


@login_required_unless_public
@xframe_options_sameorigin
def download_dataset_hdf5(request, dataset_id):
    try:
        dataset = HTSDataset.objects.get(pk=dataset_id, deleted_date=None)

        _assert_has_perm(request, dataset, 'download_data')

        df_data = df_doses_assays_controls(
            dataset=dataset,
            drug_id=None,
            cell_line_id=None,
            assay=None,
            for_export=True
        )

        with tempfile.NamedTemporaryFile('wb',
                                         dir=settings.DOWNLOADS_ROOT,
                                         prefix='h5dset',
                                         suffix='.h5',
                                         delete=False) as tf:
            tf.close()
            tmp_filename = tf.name
            write_hdf(df_data, tmp_filename)

        output_filename = '{}.h5'.format(dataset.name)

        return serve_file(request, tmp_filename, rename_to=output_filename,
                          content_type='application/x-hdf5')
    except HTSDataset.DoesNotExist:
        raise Http404()
    except NoDataException:
        response = HttpResponse('No data found for this request',
                                content_type='text/plain')
        response['Content-Disposition'] = 'attachment; filename=failed.txt'
        response['Set-Cookie'] = 'fileDownload=true; path=/'
        return response
