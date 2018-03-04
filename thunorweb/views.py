from django.shortcuts import render, redirect, Http404
from django.template.response import TemplateResponse
from django.template.loader import get_template
from django.contrib import auth
from django.contrib.auth.models import Group
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest, \
    HttpResponseServerError, HttpResponseNotFound
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, F, Count, Max
from django.utils.html import strip_tags
from .models import HTSDataset, PlateFile, Plate, CellLine, Drug, \
    Well, WellMeasurement, WellDrug, CellLineTag, DrugTag, WellStatistic
from django.urls import reverse
import json
from thunor.plots import plot_time_course, plot_dip, plot_dip_params, \
    plot_ctrl_dip_by_plate, plot_plate_map, \
    PARAM_NAMES, IC_REGEX, EC_REGEX, E_REGEX, E_REL_REGEX
from thunor.dip import dip_fit_params, AAFitWarning, \
    DrugCombosNotImplementedError
from thunor.io import write_hdf, PlateData
from thunor.helpers import plotly_to_dataframe
from plotly.utils import PlotlyJSONEncoder
from .pandas import df_doses_assays_controls, df_dip_rates, \
    df_ctrl_dip_rates, NoDataException
from .tasks import precalculate_dip_rates
from .plate_parsers import PlateFileParser
import numpy as np
import datetime
import math
from django.utils import timezone
from operator import itemgetter
from django.conf import settings
import thunorweb
import logging
import warnings
import xlsxwriter
import tempfile
from .serve_file import serve_file
from django.contrib.sites.shortcuts import get_current_site
from collections import OrderedDict, defaultdict, namedtuple
from .helpers import AutoExtendList
from guardian.shortcuts import get_objects_for_group, get_perms, \
    get_groups_with_perms, assign_perm, remove_perm, ObjectPermissionChecker
from django.contrib.contenttypes.models import ContentType
from django.views.decorators.clickjacking import xframe_options_sameorigin

logger = logging.getLogger(__name__)

SECONDS_IN_DAY = 86400


def _assert_has_perm(request, dataset, perm_required):
    if dataset.deleted_date is not None:
        raise Http404()
    if not settings.LOGIN_REQUIRED and not \
            request.user.is_authenticated():
        anon_group = Group.objects.get(name='Public')
        anon_perm_checker = ObjectPermissionChecker(anon_group)
        if not anon_perm_checker.has_perm(perm_required, dataset):
            raise Http404()
    elif dataset.owner_id != request.user.id and not \
            request.user.has_perm(
                perm_required, dataset):
        raise Http404()


def login_required_unless_public(func):
    def wrap(*args, **kwargs):
        if settings.LOGIN_REQUIRED:
            return login_required(func)(*args, **kwargs)
        else:
            return func(*args, **kwargs)
    return wrap


def handler404(request):
    if request.is_ajax():
        return JsonResponse({}, status=404)
    else:
        return HttpResponseNotFound(render(request, 'error404.html', {}))


def handler500(request):
    if request.is_ajax():
        return JsonResponse({'error': 'Internal server error'}, status=500)
    else:
        return HttpResponseServerError(render(request, 'error500.html', {}))


@login_required_unless_public
def home(request):
    user_has_datasets = HTSDataset.objects.filter(
        owner=request.user.id, deleted_date=None).exists()
    return render(request, 'home.html', {'user_has_datasets':
                                         user_has_datasets,
                                         'back_link': False})


@login_required
def my_account(request):
    return render(request, 'my_account.html')


def logout(request):
    auth.logout(request)
    return redirect('thunorweb:home')


@login_required
def dataset_upload(request, dataset_id=None):
    plate_files = None
    dataset = None
    if dataset_id:
        plate_files = list(PlateFile.objects.filter(dataset_id=dataset_id,
                                        dataset__owner_id=request.user.id).select_related('dataset'))
        if plate_files:
            dataset = plate_files[0].dataset
        else:
            try:
                dataset = HTSDataset.objects.get(id=dataset_id,
                                                 owner_id=request.user.id,
                                                 deleted_date=None)
            except HTSDataset.DoesNotExist:
                raise Http404()

    return render(request, 'plate_upload.html', {'dataset': dataset,
                                                 'plate_files': plate_files})


@transaction.atomic
def ajax_upload_platefiles(request):
    if not request.user.is_authenticated():
        return JsonResponse({}, status=401)

    dataset_id = request.POST.get('dataset_id')
    files = request.FILES.getlist('file_field[]')
    single_file_upload = len(files) == 1

    try:
        dataset = HTSDataset.objects.get(owner=request.user, id=dataset_id,
                                         deleted_date=None)
    except (ValueError, HTSDataset.DoesNotExist):
        return JsonResponse({'error': 'Dataset %s does not exist or '
                                      'you do not have access' % dataset_id,
                             'errorkeys': list(range(len(files)))})

    initial_preview_config = []

    preview_template = get_template('ajax_upload_template.html')
    initial_previews = []
    errors = {}
    pfp = PlateFileParser(files, dataset=dataset)
    results = pfp.parse_all()
    some_success = False
    for f_idx, res in enumerate(results):
        if res['success']:
            some_success = True
            initial_previews.append(preview_template.render({
                'plate_file_format': res['file_format']}))
            initial_preview_config.append({'key': res['id'], 'caption':
                                           res['file_name']})
        else:
            if single_file_upload:
                return JsonResponse({'error': str(res['error'])})
            else:
                initial_previews.append(preview_template.render({'failed':
                                                                     True}))
                initial_preview_config.append({'caption': files[f_idx].name})
                errors[f_idx] = 'File {} had error: {}'.format(
                    files[f_idx].name, str(res['error']))

    if some_success:
        # TODO: Hand this off to celery for asynchronous processing
        precalculate_dip_rates(dataset)

    response = {
        'initialPreview': initial_previews,
        'initialPreviewConfig': initial_preview_config}

    if errors:
        response['error'] = '<br>'.join(errors.values())
        response['errorkeys'] = list(errors.keys())

    return JsonResponse(response)


def ajax_delete_dataset(request):
    if not request.user.is_authenticated():
        return JsonResponse({}, status=401)

    dataset_id = request.POST.get('dataset_id')
    try:
        n_updated = HTSDataset.objects.filter(
            id=dataset_id, owner_id=request.user.id).update(
            deleted_date=timezone.now())
    except ValueError:
        raise Http404()

    if n_updated < 1:
        raise Http404()

    logger.info('Dataset deleted', extra={'request': request})

    messages.success(request, 'Dataset deleted successfully')

    return JsonResponse({'success': True})


def ajax_delete_platefile(request):
    if not request.user.is_authenticated():
        return JsonResponse({}, status=401)

    platefile_id = request.POST.get('key', None)
    try:
        n_deleted, _ = PlateFile.objects.filter(
            id=platefile_id,
            dataset__owner_id=request.user.id,
            dataset__deleted_date=None
        ).delete()
    except ValueError:
        raise Http404()

    if n_deleted < 1:
        raise Http404()

    logger.info('Platefile deleted', extra={'request': request})

    return JsonResponse({'success': True})


@transaction.atomic
def ajax_save_plate(request):
    if not request.user.is_authenticated():
        return JsonResponse({}, status=401)

    plate_data = json.loads(request.body.decode(request.encoding))

    plate_id = None
    apply_mode = 'normal'
    if plate_data.get('applyTemplateTo', None):
        # Apply data to multiple plates
        plate_ids = [int(p_id) for p_id in plate_data['applyTemplateTo']]
        apply_mode = plate_data.get('applyTemplateMode', 'all')
        if len(plate_ids) == 0:
            raise Http404()
        elif len(plate_ids) == 1:
            plate_id = plate_ids[0]
    else:
        # Apply data to single plate
        plate_id = int(plate_data['plateId'])
        plate_ids = [plate_id, ]

    wells = plate_data['wells']

    # Check permissions
    if plate_id is not None:
        pl_objs = Plate.objects.filter(id=plate_id)
    else:
        pl_objs = Plate.objects.filter(id__in=plate_ids)
    pl_objs = pl_objs.filter(dataset__owner_id=request.user.id,
                             dataset__deleted_date=None)

    pre_mod_savepoint = None
    if apply_mode != 'normal':
        pre_mod_savepoint = transaction.savepoint()
    n_updated = pl_objs.update(last_annotated=timezone.now())

    if n_updated != len(plate_ids):
        raise Exception('Query did not update the expected number of objects')

    if apply_mode != 'normal':
        # If we're applying a template, check the target plates are empty
        # Get plate names where plate has >0 cell lines specified
        if apply_mode in ['all', 'celllines']:
            cl_pl_names = Well.objects.filter(plate_id__in=plate_ids,
                                              cell_line__isnull=False).\
                values('plate').annotate(total=Count('plate')).\
                values_list('plate__name', flat=True)
        else:
            cl_pl_names = []

        # Similarly, get plate names where plate has >0 drugs specified
        if apply_mode != 'celllines':
            if apply_mode == 'drugs':
                q_clause = Q(drug__isnull=False)
            elif apply_mode == 'doses':
                q_clause = Q(dose__isnull=False)
            else:
                q_clause = Q(drug__isnull=False) | Q(dose__isnull=False)
            dr_pl_names = WellDrug.objects.filter(
                well__plate_id__in=plate_ids)\
                .filter(q_clause)\
                .values('well__plate_id')\
                .annotate(total=Count('well__plate_id'))\
                .values_list('well__plate__name', flat=True)
        else:
            dr_pl_names = []

        non_empty_plates = set(list(cl_pl_names) + list(dr_pl_names))
        if len(non_empty_plates) > 0:
            transaction.savepoint_rollback(pre_mod_savepoint)
            return JsonResponse({'error': 'non_empty_plates', 'plateNames':
                                 list(non_empty_plates)}, status=409)

    # TODO: Validate supplied cell line and drug IDs?

    # Add the cell lines
    if apply_mode not in ['drugs', 'doses']:
        cell_line_ids = [well['cellLine'] for well in wells]
        for cl_id in set(cell_line_ids):
            Well.objects.filter(
                plate_id__in=plate_ids,
                well_num__in=np.where([this_id == cl_id for this_id in
                                   cell_line_ids])[0]).update(
                                                        cell_line_id=cl_id)

    # Since we don't know how many drugs in each well there were previously
    # in the case of an update, the easy
    # solution is just to delete/reinsert. The alternative would be select
    # for update, then delete/update/insert as appropriate, which would
    # probably be slower anyway due to the extra queries.
    if apply_mode != 'celllines':
        well_drugs_to_create = defaultdict(AutoExtendList)

        if apply_mode in ['drugs', 'doses']:
            # If this is applying a template to multiple plates,
            # we'll need to get the existing well information before the
            # delete
            for wd in WellDrug.objects.filter(well__plate_id__in=plate_ids):
                if apply_mode == 'drugs' and wd.dose is not None:
                    well_drugs_to_create[(wd.well_id, wd.order)] = \
                        [None, wd.dose]
                elif apply_mode == 'doses' and wd.drug_id is not None:
                    well_drugs_to_create[(wd.well_id, wd.order)] = \
                        [wd.drug_id, None]

        WellDrug.objects.filter(well__plate_id__in=plate_ids).delete()

        well_dict = {}
        for w in Well.objects.filter(plate_id__in=plate_ids):
            well_dict[(w.plate_id, w.well_num)] = w.id

        for i, well in enumerate(wells):
            drugs = well.get('drugs', [])
            if drugs is None:
                drugs = []
            doses = well.get('doses', [])
            if doses is None:
                doses = []
            if len(drugs) == 0 and len(doses) == 0:
                continue
            for drug_order in range(max(len(drugs), len(doses))):
                drug_id = drugs[drug_order] if drug_order < len(drugs) else None
                dose = doses[drug_order] if drug_order < len(doses) else None
                if drug_id is None and dose is None:
                    continue

                for p_id in plate_ids:
                    if apply_mode != 'doses' and drug_id is not None:
                        well_drugs_to_create[(well_dict[(p_id, i)],
                                              drug_order)][0] = drug_id
                    if apply_mode != 'drugs' and dose is not None:
                        well_drugs_to_create[(well_dict[(p_id, i)],
                                              drug_order)][1] = dose

        WellDrug.objects.bulk_create([
            WellDrug(well_id=k[0], order=k[1], drug_id=v[0], dose=v[1] if
                     len(v) > 1 else None) for k, v in
                     well_drugs_to_create.items()])

    if apply_mode != 'normal':
        # If this was a template-based update...
        return JsonResponse({'success': True, 'templateAppliedTo': plate_ids})

    if plate_data.get('loadNext', None):
        next_plate_id = plate_data['loadNext']
        return ajax_load_plate(request, plate_id=next_plate_id,
                               extra_return_args={'savedPlateId': plate_id})
    else:
        return JsonResponse({'success': True, 'savedPlateId': plate_id})

    # TODO: Validate received PlateMap further?


def ajax_load_plate(request, plate_id, extra_return_args=None,
                    return_as_platedata=False, use_names=False):
    if not request.user.is_authenticated() and settings.LOGIN_REQUIRED:
        return JsonResponse({}, status=401)

    try:
        p = Plate.objects.filter(id=plate_id).select_related('dataset').get()
    except Plate.DoesNotExist:
        raise Http404()

    _assert_has_perm(request, p.dataset, 'view_plate_layout')

    field_ext = '__name' if use_names else '_id'

    # Blank well data
    wells = []
    for cl in range(p.num_wells):
        wells.append({'cellLine': None,
                      'drugs': AutoExtendList(),
                      'doses': AutoExtendList(),
                      'dipRate': None})

    # Populate cell lines
    cl_query = Well.objects.filter(plate_id=plate_id).values(
        'well_num', 'cell_line' + field_ext)
    for w in cl_query:
        wells[w['well_num']]['cellLine'] = w['cell_line' + field_ext]

    # Populate drugs
    drugs = WellDrug.objects.filter(well__plate_id=plate_id).values(
        'well__well_num', 'drug' + field_ext, 'order', 'dose')
    for dr in drugs:  # prefetched above
        wells[dr['well__well_num']]['drugs'][dr['order']] = dr['drug' +
                                                               field_ext]
        wells[dr['well__well_num']]['doses'][dr['order']] = dr['dose']

    # Populate DIP rates
    for ws in WellStatistic.objects.filter(
            well__plate_id=plate_id, stat_name='dip_rate'
    ).values('well__well_num', 'value'):
        # Need to remove NaNs for proper JSON support
        wells[ws['well__well_num']]['dipRate'] = ws['value'] if \
            ws['value'] is not None and not math.isnan(ws['value']) else None

    plate = {'datasetName': p.dataset.name,
             'plateId': p.id,
             'plateName': p.name,
             'numCols': p.width,
             'numRows': p.height,
             'wells': wells}

    if return_as_platedata:
        return PlateData.from_dict(plate)

    return_dict = {'success': True, 'plateMap': plate}
    if extra_return_args is not None:
        return_dict.update(extra_return_args)

    return JsonResponse(return_dict)


def ajax_create_dataset(request):
    if not request.user.is_authenticated():
        return JsonResponse({}, status=401)

    name = request.POST.get('name')
    if not name:
        return HttpResponseBadRequest()
    dset = HTSDataset.objects.create(owner=request.user, name=name)
    return JsonResponse({'name': dset.name, 'id': dset.id})


def ajax_create_cellline(request):
    if not request.user.is_authenticated():
        return JsonResponse({}, status=401)

    name = request.POST.get('name')
    if not name:
        return HttpResponseBadRequest()
    CellLine.objects.get_or_create(name=name)
    cell_lines = CellLine.objects.order_by('name').values('id', 'name')
    return JsonResponse({'cellLines': list(cell_lines)})


def ajax_create_drug(request):
    if not request.user.is_authenticated():
        return JsonResponse({}, status=401)

    name = request.POST.get('name')
    if not name:
        return HttpResponseBadRequest()
    Drug.objects.get_or_create(name=name)
    drugs = Drug.objects.order_by('name').values('id', 'name')
    return JsonResponse({'drugs': list(drugs)})


def ajax_get_datasets(request):
    if not request.user.is_authenticated():
        return JsonResponse({}, status=401)

    datasets = HTSDataset.objects.filter(owner_id=request.user.id,
                                         deleted_date=None).values(
        'id', 'name', 'creation_date')

    return JsonResponse({'data': list(datasets)})


def ajax_get_datasets_group(request, group_id):
    if group_id == 'Public' and (request.user.is_authenticated() or
                                 not settings.LOGIN_REQUIRED):
        group = Group.objects.get(name='Public')
    else:
        try:
            group = request.user.groups.get(pk=group_id)
        except Group.DoesNotExist:
            return JsonResponse({}, status=404)

    try:
        datasets = get_objects_for_group(
            group,
            HTSDataset.view_dataset_permission_names(),
            klass=HTSDataset,
            any_perm=True
        ).filter(deleted_date=None).values('id', 'name', 'creation_date')
    except ContentType.DoesNotExist:
        return JsonResponse({'data': list()})

    return JsonResponse({'data': list(datasets)})


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
        fit_params = dip_fit_params(
            ctrl_dip_data, expt_dip_data,
            include_dip_rates=False
        )
        # Remove -ve AA values
        fit_params.loc[fit_params['aa'] < 0.0, 'aa'] = np.nan

        # Filter for the default list of parameters only
        fit_params = fit_params.filter(items=PARAM_NAMES.keys())

        response = HttpResponse(fit_params.to_csv(), content_type='text/csv')
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


class DatasetXlsxWriter(object):
    def __init__(self, request, dataset_id, prefix=None):
        try:
            self.dataset = HTSDataset.objects.filter(id=dataset_id,
                                                     deleted_date=None)\
                .annotate(last_upload=Max('platefile__upload_date'),
                          last_annotated=Max(
                              'plate__last_annotated')).select_related(
                'owner').get()
        except HTSDataset.DoesNotExist:
            raise Http404()

        if self.dataset.owner_id != request.user.id and not \
                request.user.has_perm('download_data', self.dataset):
            raise Http404()

        self.site = get_current_site(request)
        self.prefix = prefix
        self.request_user = request.user

    def __enter__(self):
        self.tempfile = tempfile.NamedTemporaryFile('wb',
                                                    dir=settings.DOWNLOADS_ROOT,
                                                    prefix=self.prefix,
                                                    suffix='.xlsx',
                                                    delete=False)
        self.workbook = xlsxwriter.Workbook(self.tempfile)
        ws = self.workbook.add_worksheet('File Information')

        self.metadata = OrderedDict([
            ('Dataset', '{}'.format(self.dataset.name)),
            ('Dataset created by', '{} (ID: {})'.format(
                self.dataset.owner.email, self.dataset.owner.id)),
            ('Dataset created on', self.dataset.creation_date),
            ('Generated by', '{} ({})'.format(self.site.name,
                                              self.site.domain)),
            ('Software version', thunorweb.__version__),
            ('Downloaded by', '{} (ID: {})'.format(
                             self.request_user.email, self.request_user.id)),
            ('Downloaded on', timezone.now()),
            ('Last upload', self.dataset.last_upload),
            ('Last annotation', self.dataset.last_annotated)
        ])

        self.styles = {'header': self.workbook.add_format({'bold': 1}),
                       'duration': self.workbook.add_format(
                           {'num_format': '[h]:mm:ss'}),
                       'header_duration': self.workbook.add_format(
                           {'bold': 1, 'num_format': '[h]:mm:ss'}),
                       'datetime': self.workbook.add_format(
                           {'num_format': 'yyyy-mm-dd hh:mm:ss'})}

        for i, key in enumerate(self.metadata):
            ws.write(i, 0, key, self.styles['header'])
            val = self.metadata[key]
            if isinstance(val, datetime.datetime):
                (dt, tz) = self.make_datetime_naive(val)
                ws.write(i, 1, dt, self.styles['datetime'])
                ws.write(i, 2, tz)
            else:
                ws.write(i, 1, val)

        return self

    @staticmethod
    def make_datetime_naive(dt):
        tz = dt.tzname()
        return dt.replace(tzinfo=None), tz

    def __exit__(self, exc_type, exc_val_, exc_tb):
        self.workbook.close()
        self.tempfile.close()


@login_required_unless_public
@xframe_options_sameorigin
def xlsx_get_annotation_data(request, dataset_id):
    with DatasetXlsxWriter(request, dataset_id, prefix='xlsxannot-') as xlsx:
        tmp_filename = xlsx.tempfile.name
        output_filename = '{}-annotation.xlsx'.format(xlsx.dataset.name)

        plates = list(Plate.objects.filter(dataset_id=dataset_id)
                                   .order_by('id'))

        plate_ids = [p.id for p in plates]

        cell_lines = list(Well.objects.filter(plate_id__in=plate_ids)
                                              .order_by('plate_id',
                                                        'well_num'))

        drugs = list(WellDrug.objects.filter(well__plate_id__in=plate_ids)
                     .select_related('well')
                     .order_by('well__plate_id', 'well__well_num'))

        cl_pos = 0
        dr_pos = 0
        header = xlsx.styles['header']

        for p in plates:
            ws = xlsx.workbook.add_worksheet(p.name)
            ws.write(0, 0, 'Well', header)
            ws.write(0, 1, 'Cell Line', header)
            max_num_drugs = 0

            for well in p.well_iterator():
                w_id = well['well']
                ws.write(w_id+1, 0, '{}{}'.format(well['row'], well['col']))

                if cl_pos < len(cell_lines):
                    cl = cell_lines[cl_pos]
                    if cl.plate_id == p.id and cl.well_num == w_id:
                        ws.write(w_id+1, 1, cl.cell_line.name if cl.cell_line
                                 else '')
                        cl_pos += 1

                if dr_pos < len(drugs):
                    drugs_this_well = 0
                    while dr_pos < len(drugs) \
                            and drugs[dr_pos].well.plate_id == p.id \
                            and drugs[dr_pos].well.well_num == w_id:
                        drugs_this_well += 1
                        if drugs_this_well > max_num_drugs:
                            max_num_drugs += 1
                            ws.write(0, 2 * drugs_this_well,
                                     'Drug {}'.format(drugs_this_well),
                                     header)
                            ws.write(0, 2 * drugs_this_well + 1,
                                     'Dose {} (M)'.format(drugs_this_well),
                                     header)

                        ws.write(w_id + 1, 2 * drugs_this_well,
                                 drugs[dr_pos].drug.name)
                        ws.write(w_id + 1, 2 * drugs_this_well + 1,
                                 drugs[dr_pos].dose)
                        dr_pos += 1

    return serve_file(request, tmp_filename, rename_to=output_filename,
                      content_type='application/vnd.openxmlformats'
                                   '-officedocument.spreadsheetml.sheet')


@login_required_unless_public
@xframe_options_sameorigin
def xlsx_get_assay_data(request, dataset_id):
    with DatasetXlsxWriter(request, dataset_id, prefix='xlsxassay-') as xlsx:
        tmp_filename = xlsx.tempfile.name
        output_filename = '{}-assays.xlsx'.format(xlsx.dataset.name)

        assays = list(WellMeasurement.objects.filter(
            well__plate__dataset_id=dataset_id,
        ).order_by('well__plate_id', 'assay', 'timepoint',
                   'well__well_num').select_related('well', 'well__plate'))

        header = xlsx.styles['header']
        header_duration = xlsx.styles['header_duration']

        last_plate = None
        last_assay = None
        last_time = None
        last_time_col = 0

        for val in assays:

            if val.well.plate_id != last_plate:
                last_plate = val.well.plate_id
                last_assay = None
                last_time = None
                last_time_col = 0

            if val.assay != last_assay:
                last_assay = val.assay
                plate_name = '{}-{}'.format(val.well.plate.name, val.assay)
                for c in '[]:*?/\\':
                    plate_name = plate_name.replace(c, '_')
                try:
                    ws = xlsx.workbook.add_worksheet(plate_name)
                except Exception as e:
                    if str(e).find('already in use') > -1:
                        i = 1
                        succeed = False
                        while not succeed:
                            plate_name += '-{}'.format(i)
                            try:
                                ws = xlsx.workbook.add_worksheet(plate_name)
                                succeed = True
                            except:
                                i += 1
                    else:
                        raise e
                ws.write(0, 0, 'Well', header)
                last_time = None
                last_time_col = 0

            if val.timepoint != last_time:
                last_time = val.timepoint
                last_time_col += 1
                ws.write(0, last_time_col,
                    val.timepoint.total_seconds() / SECONDS_IN_DAY,
                         header_duration)

            ws.write(val.well.well_num + 1, 0, val.well.plate.well_id_to_name(
                val.well.well_num))
            ws.write(val.well.well_num + 1, last_time_col, val.value)

    return serve_file(request, tmp_filename, rename_to=output_filename,
                      content_type='application/vnd.openxmlformats'
                                   '-officedocument.spreadsheetml.sheet')


@login_required_unless_public
def plate_designer(request, dataset_id, num_wells=None):
    editable = True
    plate_sizes = []
    if dataset_id is None:
        if num_wells is None:
            return render(request, 'plate_designer_choose_size.html')
        num_wells = int(num_wells)
        if num_wells == 384:
            plates = [Plate(id='MASTER', width=24, height=16)]
        elif num_wells == 96:
            plates = [Plate(id='MASTER', width=12, height=8)]
        else:
            raise Http404()
        dataset = None
        plate_sizes.append({'numCols': plates[0].width,
                            'numRows': plates[0].height,
                            'numWells': num_wells})
    else:
        plates = list(Plate.objects.filter(dataset_id=dataset_id).order_by(
            'id').select_related('dataset'))
        if plates:
            dataset = plates[0].dataset
        else:
            try:
                dataset = HTSDataset.objects.get(pk=dataset_id)
            except HTSDataset.DoesNotExist:
                raise Http404()

        if dataset.deleted_date is not None:
            raise Http404()
        if dataset.owner_id != request.user.id:
            editable = False
            _assert_has_perm(request, dataset, 'view_plate_layout')

        for plate in plates:
            plate_size_exists = False
            for pl in plate_sizes:
                if pl['numCols'] == plate.width and pl['numRows'] == \
                        plate.height and pl['numWells'] == plate.num_wells:
                    plate_size_exists = True
            if not plate_size_exists:
                plate_sizes.append({'numCols': plate.width,
                                    'numRows': plate.height,
                                    'numWells': plate.num_wells})

        plate_sizes = sorted(plate_sizes, key=itemgetter('numWells'))

    response = TemplateResponse(request, 'plate_designer.html', {
        'num_wells': num_wells,
        'dataset': dataset,
        'editable': editable,
        'plate_sizes': plate_sizes,
        'plates': plates,
        'cell_lines': list(CellLine.objects.all().values('id', 'name')),
        'drugs': list(Drug.objects.all().values('id', 'name'))
    })
    return response


@login_required_unless_public
def view_dataset(request, dataset_id):
    try:
        dataset = HTSDataset.objects.filter(id=dataset_id, deleted_date=None)\
        .select_related('owner')\
        .annotate(last_upload=Max('platefile__upload_date'),
                  last_annotated=Max('plate__last_annotated')).get()
    except HTSDataset.DoesNotExist:
        raise Http404()

    perms_base = dataset.view_dataset_permission_names()

    if dataset.owner_id == request.user.id:
        perms = perms_base
    else:
        if not settings.LOGIN_REQUIRED and not request.user.is_authenticated():
            perms = get_perms(Group.objects.get(name='Public'), dataset)
        else:
            perms = get_perms(request.user, dataset)
        if not (set(perms_base) & set(perms)):
            raise Http404()

    response = render(request, 'dataset.html',
                      {'dataset': dataset, 'perms': perms,
                       'back_link': ["home page", reverse('thunorweb:home')]})
    return response


@login_required
def view_dataset_permissions(request, dataset_id):
    try:
        dataset = HTSDataset.objects.get(id=dataset_id, deleted_date=None)
    except HTSDataset.DoesNotExist:
        raise Http404()

    if dataset.owner_id != request.user.id:
        raise Http404()

    available_perms = HTSDataset.view_dataset_permission_names()

    all_groups = request.user.groups.all()
    groups_with_perms = get_groups_with_perms(dataset, True)

    group_perms = {}
    for gr in all_groups:
        matching_gr_perms = groups_with_perms.get(gr, [])
        group_perms[gr] = [(perm, perm in matching_gr_perms) for perm in
                           available_perms.keys()]

    response = render(request, 'dataset-permissions.html', {
        'dataset': dataset, 'available_perms': available_perms,
         'group_perms': group_perms})

    return response


@login_required
def ajax_set_dataset_group_permission(request):
    try:
        dataset_id = int(request.POST['dataset_id'])
        group_id = int(request.POST['group_id'])
        perm_id = request.POST['perm_id']
        state = request.POST['state'].lower() == 'true'
    except (KeyError, ValueError):
        return JsonResponse({'error': 'Malformed Request'}, status=400)

    try:
        dataset = HTSDataset.objects.get(pk=dataset_id, deleted_date=None,
                                         owner=request.user)
    except HTSDataset.DoesNotExist:
        raise Http404()

    # Is user a member of the requested group?
    try:
        group = request.user.groups.get(pk=group_id)
    except Group.DoesNotExist:
        raise Http404()

    # Assign or remove the permission as requested
    permission_fn = assign_perm if state else remove_perm
    permission_fn(perm_id, group, dataset)

    return JsonResponse({'success': True})


@login_required_unless_public
def ajax_get_dataset_groupings(request, dataset_id, dataset2_id=None):
    dataset_ids = [dataset_id]
    if dataset2_id is not None:
        dataset_ids.append(dataset2_id)
    try:
        plates = Plate.objects.filter(
            dataset__in=dataset_ids).select_related('dataset')
    except Plate.DoesNotExist:
        raise Http404()

    datasets = set([p.dataset for p in plates])

    if len(datasets) != len(dataset_ids):
        raise Http404()

    for dataset in datasets:
        _assert_has_perm(request, dataset, 'view_plots')

    cell_lines = Well.objects.filter(
        cell_line__isnull=False,
        plate__dataset_id__in=dataset_ids).values(
        'cell_line_id', 'cell_line__name').distinct().order_by(
        'cell_line__name')

    if request.user.is_authenticated():
        tag_owner_filter = Q(owner=request.user) | Q(owner=None)
    else:
        tag_owner_filter = Q(owner=None)

    cell_line_tags = CellLineTag.objects.filter(tag_owner_filter).filter(
        cell_line_id__in=[cl['cell_line_id'] for cl in cell_lines]
    ).values_list('owner_id', 'tag_name').distinct().order_by(
        'owner_id', 'tag_name')

    # Get drug without combinations
    drug_objs = WellDrug.objects.filter(
        drug__isnull=False,
        dose__isnull=False,
        well__plate__dataset_id__in=dataset_ids,
    ).annotate(num_drugs=Count('well__welldrug')).filter(num_drugs=1).\
      annotate(max_dose=Max('well__welldrug__dose')).filter(max_dose__gt=0).\
      values('drug_id', 'drug__name').distinct().order_by('drug__name')

    drug_tags = DrugTag.objects.filter(tag_owner_filter).filter(
        drug_id__in=[dr['drug_id'] for dr in drug_objs]
    ).values_list('owner_id', 'tag_name').distinct().order_by(
        'owner_id', 'tag_name')

    assays = WellMeasurement.objects.filter(
        well__plate__dataset_id__in=dataset_ids
    ).values('assay').distinct().order_by('assay')

    drug_list = [{'id': dr['drug_id'], 'name': dr['drug__name']} for dr in
                 drug_objs]

    # Get drugs with combinations... this is inefficient but works
    # for arbitrary numbers of drugs per well
    drug_objs_combos = WellDrug.objects.filter(
        drug__isnull=False,
        dose__isnull=False,
        well__plate__dataset_id__in=dataset_ids
    ).annotate(drug2_id=F('well__welldrug__drug_id')
    ).exclude(drug_id=F('drug2_id')).values(
        'well_id', 'drug_id', 'drug__name') \
        .distinct()

    drug_well_combos = defaultdict(set)
    for d in drug_objs_combos:
        drug_well_combos[d['well_id']].add((d['drug_id'], d['drug__name']))

    drug_combos = set(frozenset(d) for d in drug_well_combos.values())

    for dc in drug_combos:
        drug_ids, drug_names = zip(*sorted(dc, key=lambda d: d[1]))
        drug_list.append({'id': drug_ids, 'name': drug_names})

    return JsonResponse({
        'datasets': [{'id': d.id, 'name': d.name} for d in datasets],
        'cellLines': [{'id': cl['cell_line_id'],
                       'name': cl['cell_line__name']} for cl in cell_lines],
        'cellLineTags': [{'id': ('1' if tag[0] is None else '0') + tag[1],
                          'name': tag[1],
                          'public': tag[0] is None}
                         for tag in cell_line_tags],
        'drugs': drug_list,
        'drugTags': [{'id': ('1' if tag[0] is None else '0') + tag[1],
                      'name': tag[1],
                      'public': tag[0] is None}
                     for tag in drug_tags],
        'assays': [{'id': a['assay'], 'name': a['assay']} for a in assays],
        'plates': [{'id': p.id, 'name': p.name} for p in plates]
    })


@login_required_unless_public
def ajax_get_plot(request, file_type='json'):
    if file_type in ('csv', 'json'):
        permission_required = 'download_data'
    else:
        permission_required = 'view_plots'

    try:
        plot_type = request.GET['plotType']

        dataset_id = int(request.GET['datasetId'])
        dataset2_id = request.GET.get('dataset2Id', None)
        if dataset2_id == "":
            dataset2_id = None
        if dataset2_id is not None:
            dataset2_id = int(dataset2_id)
        cell_line_id = request.GET.getlist('cellLineId')
        cell_line_tag_names = request.GET.getlist('cellLineTags')
        aggregate_cell_lines = request.GET.get('aggregateCellLines', False) \
                               == "true"
        if not cell_line_id and cell_line_tag_names:
            public_cell_line_tags = [t[1:] for t in cell_line_tag_names if
                                     t[0] == '1']
            private_cell_line_tags = [t[1:] for t in cell_line_tag_names if
                                      t[0] == '0']
            cell_line_tag_base_query = CellLineTag.objects.filter(
                owner=None, tag_name__in=public_cell_line_tags
            )
            if private_cell_line_tags and request.user.is_authenticated():
                cell_line_tag_base_query |= CellLineTag.objects.filter(
                    owner=request.user, tag_name__in=private_cell_line_tags)
            if not aggregate_cell_lines:
                cell_line_id = cell_line_tag_base_query.distinct(
                ).values_list(
                    'cell_line_id', flat=True)
            else:
                cell_line_tag_objs = cell_line_tag_base_query.values_list(
                    'tag_name', 'cell_line_id', 'cell_line__name')
                cell_line_id = [cl[1] for cl in cell_line_tag_objs]
                aggregate_cell_lines = defaultdict(list)
                for tag_name, _, cl_name in cell_line_tag_objs:
                    aggregate_cell_lines[tag_name].append(cl_name)
        drug_id = request.GET.getlist('drugId')
        drug_tag_names = request.GET.getlist('drugTags')
        aggregate_drugs = request.GET.get('aggregateDrugs', False) == "true"
        if not drug_id and drug_tag_names:
            public_drug_tags = [t[1:] for t in drug_tag_names if
                                t[0] == '1']
            private_drug_tags = [t[1:] for t in drug_tag_names if
                                 t[0] == '0']
            drug_tag_base_query = DrugTag.objects.filter(
                owner=None, tag_name__in=public_drug_tags
            )
            if private_drug_tags and request.user.is_authenticated():
                drug_tag_base_query |= DrugTag.objects.filter(
                    owner=request.user, tag_name__in=private_drug_tags)
            if not aggregate_drugs:
                drug_id = drug_tag_base_query.distinct().values_list(
                    'drug_id', flat=True)
            else:
                drug_tag_objs = drug_tag_base_query.values_list(
                    'tag_name', 'drug_id', 'drug__name')
                drug_id = [dt[1] for dt in drug_tag_objs]
                aggregate_drugs = defaultdict(list)
                for tag_name, _, dr_name in drug_tag_objs:
                    aggregate_drugs[tag_name].append(dr_name)

        if plot_type != 'qc' and (cell_line_id is None or len(cell_line_id)
                == 0 or drug_id is None or len(drug_id) == 0):
            return HttpResponse('Please enter at least one cell line and '
                                'drug', status=400)

        cell_line_id = [int(cl) for cl in cell_line_id]
        drug_ids = []
        for dr in drug_id:
            try:
                drug_ids.append(int(dr))
            except ValueError:
                drug_ids.append([int(d) for d in dr.split(",")])
        drug_id = drug_ids

        assay = request.GET.get('assayId')
        yaxis = request.GET.get('logTransform', 'None')

    except (KeyError, ValueError):
        raise Http404()

    try:
        dataset = HTSDataset.objects.get(pk=dataset_id)
    except HTSDataset.DoesNotExist:
        raise Http404()

    _assert_has_perm(request, dataset, permission_required)

    if plot_type == 'tc':
        if len(drug_id) > 1 or len(cell_line_id) > 1:
            return HttpResponse('Please select exactly one cell line and '
                                'drug for time course plot', status=400)

        try:
            df_data = df_doses_assays_controls(
                dataset=dataset,
                drug_id=drug_id,
                cell_line_id=cell_line_id,
                assay=assay
            )
        except NoDataException:
            return HttpResponse('No data found for this request. This '
                                'drug/cell line/assay combination may not '
                                'exist.', status=400)
        if assay is None:
            assay = df_data.assays.index.get_level_values('assay')[0]

        overlay_dip_fit = request.GET.get('overlayDipFit', 'false') == 'true'

        if overlay_dip_fit and assay != df_data.dip_assay_name:
            return HttpResponse('Can only overlay DIP rate on cell '
                                'proliferation assays', status=400)

        plot_fig = plot_time_course(
            df_data,
            log_yaxis=yaxis == 'log2',
            assay_name=assay,
            show_dip_fit=overlay_dip_fit,
            subtitle=dataset.name
        )
    elif plot_type in ('dip', 'dippar'):
        if dataset2_id is not None:
            try:
                dataset2 = HTSDataset.objects.get(pk=dataset2_id)
            except HTSDataset.DoesNotExist:
                raise Http404()

            _assert_has_perm(request, dataset2, permission_required)

            if dataset.name == dataset2.name:
                return HttpResponse(
                    'Cannot compare two datasets with the same '
                    'name. Please rename one of the datasets.',
                    status=400)

        # Fetch the DIP rates from the DB
        dataset_ids = dataset_id if dataset2_id is None else [dataset_id,
                                                              dataset2_id]
        try:
            ctrl_dip_data, expt_dip_data = df_dip_rates(
                dataset_id=dataset_ids,
                drug_id=drug_id,
                cell_line_id=cell_line_id,
                use_dataset_names=True
            )
        except NoDataException:
            return HttpResponse('No data found for this request. This '
                                'drug/cell line/assay combination may not '
                                'exist.', status=400)

        def _setup_dip_par(name, needs_toggle=False):
            if needs_toggle and \
                            request.GET.get(name + 'Toggle', 'off') != 'on':
                return None
            par_name = request.GET.get(name, None)
            if par_name is not None and '_custom' in par_name:
                rep_value = request.GET.get(name + 'Custom', None)
                if int(rep_value) < 0:
                    raise ValueError()
                par_name = par_name.replace('_custom', rep_value)
            return par_name

        try:
            dip_par = _setup_dip_par('dipPar')
        except ValueError:
            return HttpResponse('Parameter custom value '
                                'needs to be a positive integer', status=400)

        try:
            dip_par_two = _setup_dip_par('dipParTwo', needs_toggle=True)
        except ValueError:
            return HttpResponse('Parameter two custom value '
                                'needs to be a positive integer', status=400)

        try:
            dip_par_order = _setup_dip_par('dipParOrder', needs_toggle=True)
        except ValueError:
            return HttpResponse('Parameter order custom value '
                                'needs to be a positive integer', status=400)

        # Work out any non-standard parameters we need to calculate
        # e.g. non-standard IC concentrations
        ic_concentrations = {50}
        ec_concentrations = set()
        e_values = set()
        e_rel_values = set()
        regexes = {IC_REGEX: ic_concentrations,
                   EC_REGEX: ec_concentrations,
                   E_REGEX: e_values,
                   E_REL_REGEX: e_rel_values
                   }
        for param in (dip_par, dip_par_two, dip_par_order):
            if param is None:
                continue
            for regex, value_list in regexes.items():
                match = regex.match(param)
                if not match:
                    continue
                try:
                    value = int(match.groups(0)[0])
                    if value < 0 or value > 100:
                        raise ValueError()
                    value_list.add(value)
                except ValueError:
                    return HttpResponse('Invalid custom value - must be '
                                        'an integer between 1 and 100',
                                        status=400)

        # Fit Hill curves and compute parameters
        with warnings.catch_warnings(record=True) as w:
            fit_params = dip_fit_params(
                ctrl_dip_data, expt_dip_data,
                include_dip_rates=plot_type == 'dip',
                custom_ic_concentrations=ic_concentrations,
                custom_ec_concentrations=ec_concentrations,
                custom_e_values=e_values,
                custom_e_rel_values=e_rel_values
            )
            # Currently only care about warnings if plotting AA
            if plot_type == 'dippar' and (dip_par == 'aa' or
                                          dip_par_two == 'aa'):
                w = [i for i in w if issubclass(i.category, AAFitWarning)]
                if w:
                    return HttpResponse(w[0].message, status=400)
        if plot_type == 'dippar':
            if dip_par is None:
                return HttpResponse('Dose response parameter sort field is '
                                    'required', status=400)
            try:
                plot_fig = plot_dip_params(
                    fit_params,
                    fit_param=dip_par,
                    fit_param_compare=dip_par_two,
                    fit_param_sort=dip_par_order,
                    log_yaxis=yaxis == 'log2',
                    aggregate_cell_lines=aggregate_cell_lines,
                    aggregate_drugs=aggregate_drugs,
                    multi_dataset=dataset2_id is not None
                )
            except ValueError as e:
                return HttpResponse(e, status=400)
        else:
            dip_absolute = request.GET.get('dipType', 'rel') == 'abs'
            plot_fig = plot_dip(
                fit_params,
                is_absolute=dip_absolute
            )
    elif plot_type == 'qc':
        qc_view = request.GET.get('qcView', None)
        if qc_view == 'ctrldipbox':
            ctrl_dip_data = df_ctrl_dip_rates(dataset_id)
            if ctrl_dip_data is None:
                return HttpResponse('No control wells were detected in this '
                                    'dataset.', status=400)
            plot_fig = plot_ctrl_dip_by_plate(ctrl_dip_data)
        elif qc_view == 'dipplatemap':
            plate_id = request.GET.get('plateId', None)
            try:
                plate_id = int(plate_id)
            except ValueError:
                return HttpResponse('Integer plateId required', status=400)
            pl_data = ajax_load_plate(request, plate_id,
                                      return_as_platedata=True,
                                      use_names=True)
            plot_fig = plot_plate_map(pl_data, color_by='dip_rates')
        else:
            return HttpResponse('Unimplemented QC view: {}'.format(qc_view),
                                status=400)
    else:
        return HttpResponse('Unimplemented plot type: %s' % plot_type,
                            status=400)

    as_attachment = request.GET.get('download', '0') == '1'

    if file_type == 'json':
        response = JsonResponse(plot_fig, encoder=PlotlyJSONEncoder)
    elif file_type == 'csv':
        response = HttpResponse(plotly_to_dataframe(plot_fig).to_csv(),
                                content_type='text/csv')
    elif file_type == 'html':
        response = render(request, 'plotly_plot.html',
            {'data': JsonResponse(plot_fig,
                                  encoder=PlotlyJSONEncoder).content})
    else:
        return HttpResponse('Unknown file type: %s' % file_type, status=400)

    if as_attachment:
        try:
            title = plot_fig['layout']['title']
        except KeyError:
            title = 'Plot'
        response['Content-Disposition'] = \
            'attachment; filename="{}.{}"'.format(strip_tags(title), file_type)

    return response


@login_required_unless_public
def plots(request):
    # Check the dataset exists
    dataset_id = request.GET.get('dataset', None)
    dataset2_id = request.GET.get('dataset2', None)
    dataset = None
    dataset2 = None
    if dataset_id is not None:
        try:
            dataset_id = int(dataset_id)
            if dataset2_id is not None:
                dataset2_id = int(dataset2_id)
        except ValueError:
            raise Http404()

        datasets = HTSDataset.objects.in_bulk([dataset_id, dataset2_id])

        if not datasets:
            raise Http404()

        dataset = datasets[dataset_id]
        if dataset2_id in datasets:
            dataset2 = datasets[dataset2_id]

        _assert_has_perm(request, dataset, 'view_plots')

    return render(request, 'plots.html', {'default_dataset': dataset,
                                          'second_dataset': dataset2,
                                          'navbar_hide_dataset': True})


@login_required_unless_public
def tag_editor(request, tag_type=None):
    if request.user.is_authenticated():
        tag_owner_filter = Q(owner=request.user) | Q(owner=None)
    else:
        tag_owner_filter = Q(owner=None)

    Tag = namedtuple('Tag', ['is_public', 'tag_name'])
    tag_dict_selected = defaultdict(list)
    tag_dict_all = {}
    if tag_type == 'cell_lines':
        entity_type = 'Cell Line'
        entity_type_var = 'cl'
        entity_options = CellLine.objects.all().order_by('name')
        tag_list = CellLineTag.objects.filter(tag_owner_filter).order_by(
                F('owner_id').asc(nulls_last=True), 'tag_name',
                'cell_line__name')
        for tag in tag_list:
            tag_dict_selected[Tag(tag.owner_id is None, tag.tag_name)].append(
                tag.cell_line_id)
        for tag_key, cell_lines in tag_dict_selected.items():
            tag_dict_all[tag_key] = [(ent, ent.id in cell_lines) for ent in
                                     entity_options]
    elif tag_type == 'drugs':
        entity_type = 'Drug'
        entity_type_var = 'drug'
        entity_options = Drug.objects.all().order_by('name')
        tag_list = DrugTag.objects.filter(tag_owner_filter).order_by(
                F('owner_id').asc(nulls_last=True), 'tag_name', 'drug__name')
        for tag in tag_list:
            tag_dict_selected[Tag(tag.owner_id is None, tag.tag_name)].append(
                tag.drug_id)
        for tag_key, drugs in tag_dict_selected.items():
            tag_dict_all[tag_key] = [(ent, ent.id in drugs) for ent in
                                     entity_options]
    else:
        return render(request, "tags.html")

    return render(request, "tag_editor.html",
                  {'entity_type': entity_type,
                   'entity_type_var': entity_type_var,
                   'tag_type': tag_type,
                   'tag_dict_all': tag_dict_all,
                   'entities': [(tag, False) for tag in entity_options],
                   'private_tags': [tag[1] for tag in
                                    tag_dict_selected if not tag[0]],
                   'public_tags': [tag[1] for tag in
                                   tag_dict_selected if tag[0]],
                   }
                  )


def ajax_rename_tag(request):
    if not request.user.is_authenticated():
        return JsonResponse({}, status=401)

    try:
        old_tag_name = request.POST.get('oldTagName')
        tag_name = request.POST.get('tagName')
        tag_type = request.POST.get('tagType')
        if tag_type not in ('cl', 'drug'):
            raise ValueError
    except (KeyError, ValueError):
        return JsonResponse({'error': 'Form not properly formatted'},
                            status=400)

    tag_cls = DrugTag if tag_type == 'drug' else CellLineTag

    tag_cls.objects.filter(tag_name=old_tag_name, owner=request.user).update(
        tag_name=tag_name)

    return JsonResponse({'status': 'success'})


def ajax_assign_tag(request):
    if not request.user.is_authenticated():
        return JsonResponse({}, status=401)

    try:
        tag_name = request.POST.get('tagName')
        if tag_name == '':
            raise ValueError()
        tag_type = request.POST.get('tagType')
        if tag_type not in ('cl', 'drug'):
            raise ValueError
        entity_ids = [int(e_id) for e_id in request.POST.getlist('entityId')]

        tag_public = request.POST.get('tagPublic') == '1'
    except (KeyError, ValueError):
        return JsonResponse({'error': 'Form not properly formatted'},
                            status=400)

    if tag_public and not request.user.is_staff:
        return JsonResponse({'error': 'Staff only'}, status=403)

    owner = None if tag_public else request.user

    tag_cls = DrugTag if tag_type == 'drug' else CellLineTag

    # Clear any existing instances of the tag
    tag_cls.objects.filter(tag_name=tag_name, owner=owner).delete()

    # Create the new tags
    if tag_type == 'drug':
        DrugTag.objects.bulk_create([
            DrugTag(tag_name=tag_name, owner=owner, drug_id=drug_id)
            for drug_id in entity_ids
        ])
    else:
        CellLineTag.objects.bulk_create([
            CellLineTag(tag_name=tag_name, owner=owner,
                        cell_line_id=cell_line_id)
            for cell_line_id in entity_ids
        ])

    logger.info('Tag modified', extra={'request': request})

    return JsonResponse({'status': 'success'})
