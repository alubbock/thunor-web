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
from django.db.models import Q, Count, Max
from .models import HTSDataset, PlateFile, Plate, CellLine, Drug, \
    Well, WellMeasurement, WellDrug
import json
from .plots import plot_dose_response_3d, plot_time_course, plot_dip
from .pandas import df_doses_assays_controls, NoDataException
from .plate_parsers import PlateFileParser
import numpy as np
import datetime
from django.utils import timezone
from operator import itemgetter
from django.conf import settings
import pyhts
import logging
import xlsxwriter
import tempfile
from .serve_file import serve_file
from django.contrib.sites.shortcuts import get_current_site
from collections import OrderedDict, defaultdict
from .helpers import AutoExtendList
from guardian.shortcuts import get_objects_for_group, get_perms, \
    get_groups_with_perms, assign_perm, remove_perm
from django.contrib.contenttypes.models import ContentType
from django.views.decorators.clickjacking import xframe_options_sameorigin

logger = logging.getLogger(__name__)

SECONDS_IN_DAY = 86400
# TODO: Improve this handling of controls!
KNOWN_CONTROLS = ['DMSO']


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


@login_required
def home(request):
    user_has_datasets = HTSDataset.objects.filter(
        owner=request.user.id).exists()
    return render(request, 'home.html', {'user_has_datasets':
                                         user_has_datasets})


@login_required
def my_account(request):
    return render(request, 'my_account.html')


def logout(request):
    auth.logout(request)
    return redirect('pyhts:home')


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
                                                 owner_id=request.user.id)
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
        dataset = HTSDataset.objects.get(owner=request.user, id=dataset_id)
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
    for f_idx, res in enumerate(results):
        if res['success']:
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
        n_deleted, _ = HTSDataset.objects.filter(id=dataset_id,
                                                 owner_id=request.user.id).\
            delete()
    except ValueError:
        raise Http404()

    if n_deleted < 1:
        raise Http404()

    messages.success(request, 'Dataset deleted successfully')

    return JsonResponse({'success': True})


def ajax_delete_platefile(request):
    if not request.user.is_authenticated():
        return JsonResponse({}, status=401)

    platefile_id = request.POST.get('key', None)
    try:
        n_deleted, _ = PlateFile.objects.filter(id=platefile_id,
                               dataset__owner_id=request.user.id).delete()
    except ValueError:
        raise Http404()

    if n_deleted < 1:
        raise Http404()

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
    pl_objs = pl_objs.filter(dataset__owner_id=request.user.id)

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
            drugs = well.get('drugs', None)
            doses = well.get('doses', None)
            if drugs is None and doses is None:
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

        WellDrug.objects.bulk_create([WellDrug(well_id=k[0], order=k[1],
                                               drug_id=v[0], dose=v[1] if
            len(v) > 1 else None)
                                      for
                                      k, v in well_drugs_to_create.items()])

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


def ajax_load_plate(request, plate_id, extra_return_args=None):
    if not request.user.is_authenticated():
        return JsonResponse({}, status=401)

    try:
        p = Plate.objects.filter(id=plate_id).select_related('dataset').get()
    except Plate.DoesNotExist:
        raise Http404()

    if request.user.id != p.dataset.owner_id and not request.user.has_perm(
            'view_plate_layout', p.dataset):
        raise Http404()

    cell_lines = Well.objects.filter(plate_id=plate_id).order_by(
        'well_num').values('cell_line_id')
    drugs = WellDrug.objects.filter(well__plate_id=plate_id).order_by(
        'well__well_num', 'order').values(
        'well__well_num', 'drug_id', 'order', 'dose')

    wells = []
    for cl in range(p.num_wells):
        wells += [{'cellLine': cell_lines[cl]['cell_line_id'] if cell_lines
                else None,
                   'drugs': AutoExtendList(), 'doses': AutoExtendList()}]

    assert len(wells) == p.num_wells

    for dr in drugs:
        wells[dr['well__well_num']]['drugs'][dr['order']] = dr['drug_id']
        wells[dr['well__well_num']]['doses'][dr['order']] = dr['dose']

    plate = {'plateId': p.id,
             'numCols': p.width,
             'numRows': p.height,
             'wells': wells}

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

    datasets = HTSDataset.objects.filter(owner_id=request.user.id).values(
        'id', 'name', 'creation_date')

    return JsonResponse({'data': list(datasets)})


def ajax_get_datasets_group(request, group_id):
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
        ).values('id', 'name', 'creation_date')
    except ContentType.DoesNotExist:
        return JsonResponse({'data': list()})

    return JsonResponse({'data': list(datasets)})


class DatasetXlsxWriter(object):
    def __init__(self, request, dataset_id, prefix=None):
        try:
            self.dataset = HTSDataset.objects.filter(id=dataset_id)\
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
            ('Software version', pyhts.__version__),
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


@login_required
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


@login_required
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


@login_required
def plate_designer(request, dataset_id):
    try:
        dataset = HTSDataset.objects.get(id=dataset_id)
    except HTSDataset.DoesNotExist:
        raise Http404()

    editable = True

    if dataset.owner_id != request.user.id:
        editable = False
        if not request.user.has_perm('view_plate_layout', dataset):
            raise Http404()

    plates = list(Plate.objects.filter(dataset_id=dataset_id).order_by('id'))

    plate_sizes = []
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
        'dataset': dataset,
        'editable': editable,
        'plate_sizes': plate_sizes,
        'plates': plates,
        'cell_lines': list(CellLine.objects.all().values('id', 'name')),
        'drugs': list(Drug.objects.all().values('id', 'name'))
    })
    return response


@login_required
def view_dataset(request, dataset_id):
    try:
        dataset = HTSDataset.objects.filter(id=dataset_id)\
        .annotate(last_upload=Max('platefile__upload_date'),
                  last_annotated=Max('plate__last_annotated')).get()
    except HTSDataset.DoesNotExist:
        raise Http404()

    perms_base = dataset.view_dataset_permission_names()

    if dataset.owner_id == request.user.id:
        perms = perms_base
    else:
        perms = get_perms(request.user, dataset)
        if not (set(perms_base) & set(perms)):
            raise Http404()

    response = render(request, 'dataset.html', {'dataset': dataset,
                                                'perms': perms})
    return response


@login_required
def view_dataset_permissions(request, dataset_id):
    try:
        dataset = HTSDataset.objects.get(id=dataset_id)
    except HTSDataset.DoesNotExist:
        raise Http404()

    if dataset.owner_id != request.user.id:
        raise Http404()

    available_perms = {p[0]: p[1] for p in HTSDataset._meta.permissions}

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
        dataset = HTSDataset.objects.get(pk=dataset_id)
    except HTSDataset.DoesNotExist:
        raise Http404()

    # Does user own this dataset?
    if dataset.owner_id != request.user.id:
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


def ajax_get_dataset_groupings(request, dataset_id):
    if not request.user.is_authenticated():
        return JsonResponse({}, status=401)

    try:
        dataset = HTSDataset.objects.get(pk=dataset_id)
    except HTSDataset.DoesNotExist:
        raise Http404()

    if dataset.owner_id != request.user.id:
        if not request.user.has_perm('view_plots', dataset):
            raise Http404()

    cell_lines = Well.objects.filter(
        cell_line__isnull=False,
        plate__dataset_id=dataset_id).annotate(
        num_drugs=Count('welldrug')).filter(
        num_drugs=1).select_related(
    ).values('cell_line_id', 'cell_line__name').distinct().order_by(
        'cell_line__name')

    # Get drug without combinations
    drug_objs = WellDrug.objects.filter(
        drug__isnull=False,
        dose__isnull=False,
        well__plate__dataset_id=dataset_id,
    ).annotate(num_drugs=Count('well__welldrug')).filter(num_drugs=1).\
      values('drug_id', 'drug__name').distinct().order_by('drug__name')

    if dataset.control_handling == 'A1':
        drug_objs = drug_objs.exclude(well__well_num=0)

    assays = WellMeasurement.objects.filter(
        well__plate__dataset_id=dataset_id).annotate(
        num_drugs=Count('well__welldrug')).filter(
        num_drugs=1).values('assay').distinct().order_by('assay')

    drug_list = []
    controls_list = [{'id': None, 'name': 'None'}]

    for dr in drug_objs:
        this_entry = {'id': dr['drug_id'], 'name': dr['drug__name']}
        if this_entry['name'] in KNOWN_CONTROLS:
            controls_list.append(this_entry)
        else:
            drug_list.append(this_entry)

    return JsonResponse({
        'cellLines': [{'id': cl['cell_line_id'],
                       'name': cl['cell_line__name']} for cl in cell_lines],
        'drugs': drug_list,
        'assays': [{'id': a['assay'], 'name': a['assay']} for a in assays],
        'controls': controls_list
    })


def ajax_get_plot(request):
    if not request.user.is_authenticated():
        return JsonResponse({}, status=401)

    try:
        plot_type = request.GET['plotType']

        dataset_id = int(request.GET['datasetId'])
        cell_line_id = request.GET.getlist('cellLineId')
        drug_id = request.GET.getlist('drugId')

        if cell_line_id is None and drug_id is None:
            return HttpResponse('A cell line ID or drug ID is required',
                                status=400)

        if not cell_line_id or not drug_id:
            return HttpResponse('Please enter at least one cell line and '
                               'drug', status=400)

        cell_line_id = [int(cl) for cl in cell_line_id]
        drug_id = [int(dr) for dr in drug_id]

        assay = request.GET.get('assayId')
        yaxis = request.GET.get('logTransform', 'None')
        dip_absolute = request.GET.get('dipType', 'rel') == 'abs'

    except (KeyError, ValueError):
        raise Http404()

    display_fit_params = False
    dip_par_sort = request.GET.get('dipParSort', 'ic50')

    # if plot_type == 'dr3d':
    #     plot_fn = plot_dose_response_3d
    #     plot_type_str = 'Dose/response/time'
    if plot_type == 'tc':
        plot_fn = plot_time_course
        plot_type_str = 'Time course'
        if len(drug_id) > 1 or len(cell_line_id) > 1:
            return HttpResponse('Please select exactly one cell line and '
                                'drug for time course plot', status=400)
    elif plot_type == 'dip':
        plot_fn = plot_dip
        plot_type_str = 'Dose/response'
    elif plot_type == 'dippar':
        plot_fn = plot_dip
        plot_type_str = 'Dose/response parameters'
        display_fit_params = True
    else:
        return HttpResponse('Unimplemented plot type: %s' % plot_type,
                            status=400)

    try:
        dataset = HTSDataset.objects.get(pk=dataset_id)
        if dataset.control_handling == 'A1':
            if assay is None:
                assay = 'Cell count'
            control_id = 'A1'
        elif dataset.control_handling is None:
            control_id = 0
            if assay is None:
                # TODO: This should be handled better!
                assay = 'lum:Lum'
        else:
            return HttpResponse('Unknown control handling: ' +
                                dataset.control_handling, status=400)
    except HTSDataset.DoesNotExist:
        raise Http404()

    if dataset.owner_id != request.user.id and not request.user.has_perm(
            'view_plots', dataset):
        raise Http404

    try:
        df_data = df_doses_assays_controls(
            dataset_id=dataset_id,
            drug_id=drug_id,
            cell_line_id=cell_line_id,
            assay=assay,
            control=control_id
        )

        if drug_id and len(drug_id) == 1:
            drug_name = df_data['doses'].index.get_level_values(
                'drug')[0]
            plot_type_str += ' for {}'.format(drug_name)
        if cell_line_id and len(cell_line_id) == 1:
            cell_line_name = df_data['doses'].index.get_level_values(
                'cell_line')[0]
            plot_type_str += ' on {}'.format(cell_line_name)

        return HttpResponse(plot_fn(df_data['doses'],
                                    df_data['assays'],
                                    df_data['controls'],
                                    is_absolute=dip_absolute,
                                    doublings=yaxis == 'log2',
                                    display_fit_params=display_fit_params,
                                    fit_params_sort=dip_par_sort,
                                    assay_name=assay,
                                    title=plot_type_str))
    except NoDataException:
        return HttpResponse('No data found for this request. This drug/cell '
                            'line/assay combination may not exist.',
                            status=400)
    except NotImplementedError:
        return HttpResponse('Not implemented', status=400)


@login_required
def plots(request, dataset_id):
    control_0 = WellDrug.objects.filter(
        drug__name__in=KNOWN_CONTROLS,
        well__plate__dataset__id=dataset_id
    ).select_related('well__plate__dataset', 'drug').first()

    if control_0:
        control_id = control_0.drug.id
        dataset = control_0.well.plate.dataset
    else:
        # Check the dataset exists instead
        try:
            dataset = HTSDataset.objects.get(id=dataset_id)
        except HTSDataset.DoesNotExist:
            raise Http404()

        control_id = None

    if dataset.owner_id != request.user.id:
        if not (set(dataset.view_dataset_permission_names()) &
                set(get_perms(request.user, dataset))):
            raise Http404()

    return render(request, 'plots.html', {'dataset': dataset,
                                          'control_id': control_id})
