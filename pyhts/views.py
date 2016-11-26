from django.shortcuts import render, redirect, Http404
from django.template.response import TemplateResponse
from django.template.loader import get_template
from django.contrib import auth
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest, \
    HttpResponseServerError, HttpResponseNotFound
from django.db.utils import IntegrityError
from django.db import transaction
from django.db.models import Q, Count, Max
from .models import HTSDataset, PlateFile, Plate, CellLine, Drug, \
    WellCellLine, WellMeasurement, WellDrug
import json
from .plots import plot_dose_response
from .pandas import df_dose_response
from .plate_parsers import PlateFileParser, PlateFileParseException
import numpy as np
import datetime
from django.utils import timezone
from operator import itemgetter
from django.conf import settings
import pyhts
import logging
import os
import xlsxwriter
import tempfile
from django.views.static import serve
from .serve_file import nginx_file
from django.contrib.sites.shortcuts import get_current_site
from collections import OrderedDict

logger = logging.getLogger(__name__)

SECONDS_IN_DAY = 86400


def handler404(request):
    return HttpResponseNotFound(render(request, 'error404.html', {}))


def handler500(request):
    return HttpResponseServerError(render(request, 'error500.html', {}))


@login_required
def home(request):
    return render(request, 'home.html')


@login_required
def my_account(request):
    return render(request, 'my_account.html')


def logout(request):
    auth.logout(request)
    return redirect('pyhts:home')


@login_required
def dataset_upload(request, dataset_id=None):
    plate_files = None
    if dataset_id:
        plate_files = list(PlateFile.objects.filter(dataset_id=dataset_id,
                                        dataset__owner_id=request.user.id))
        if not plate_files:
            try:
                HTSDataset.objects.get(id=dataset_id, owner_id=request.user.id)
            except HTSDataset.DoesNotExist:
                raise Http404()

    return render(request, 'plate_upload.html', {'dataset_id': dataset_id,
                                                 'plate_files': plate_files})


@login_required
@transaction.atomic
def ajax_upload_platefiles(request):
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
    for f_idx, f in enumerate(files):
        try:
            pfp = PlateFileParser(f, dataset=dataset)
            pfp.parse_platefile()
            initial_previews.append(preview_template.render({
                'plate_file_format': pfp.file_format}))
            initial_preview_config.append({'key': pfp.id, 'caption':
                                           pfp.file_name})
        except PlateFileParseException as pfpe:
            if single_file_upload:
                return JsonResponse({'error': str(pfpe)})
            else:
                initial_previews.append(preview_template.render({'failed':
                                                                     True}))
                initial_preview_config.append({'caption': f.name})
                errors[f_idx] = 'File {} had error: {}'.format(f.name,
                                                               str(pfpe))
    response = {
        'initialPreview': initial_previews,
        'initialPreviewConfig': initial_preview_config}

    if errors:
        response['error'] = '<br>'.join(errors.values())
        response['errorkeys'] = list(errors.keys())

    return JsonResponse(response)


@login_required
def ajax_delete_platefile(request):
    platefile_id = request.POST.get('key', None)
    try:
        n_deleted, _ = PlateFile.objects.filter(id=platefile_id,
                               dataset__owner_id=request.user.id).delete()
    except ValueError:
        raise Http404()

    if n_deleted < 1:
        raise Http404()

    return JsonResponse({'success': True})


@login_required
@transaction.atomic
def ajax_save_plate(request):
    plate_data = json.loads(request.body.decode(request.encoding))

    plate_id = None
    plate_ids = None
    if plate_data.get('applyTemplateTo', None):
        # Apply data to multiple plates
        plate_ids = [int(p_id) for p_id in plate_data['applyTemplateTo']]
        if len(plate_ids) == 0:
            # TODO: Raise a proper error!
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
    if plate_id is None:
        pre_mod_savepoint = transaction.savepoint()
    n_updated = pl_objs.update(last_annotated=timezone.now())

    if n_updated != len(plate_ids):
        # TODO: This should return a better error
        raise Http404()

    if plate_id is None:
        # If we're applying a template, check the target plates are empty
        # Get plate names where plate has >0 cell lines specified
        cl_pl_names = WellCellLine.objects.filter(plate_id__in=plate_ids,
                                               cell_line__isnull=False).\
            values('plate').annotate(total=Count('plate')).\
            values_list('plate__name', flat=True)

        # Similarly, get plate names where plate has >0 drugs specified
        dr_pl_names = WellDrug.objects.filter(plate_id__in=plate_ids).filter(
            Q(drug__isnull=False) | Q(dose__isnull=False)).values(
            'plate').annotate(total=Count('plate')).values_list('plate__name',
                                                                flat=True)

        non_empty_plates = set(list(cl_pl_names) + list(dr_pl_names))
        if len(non_empty_plates) > 0:
            transaction.savepoint_rollback(pre_mod_savepoint)
            return JsonResponse({'error': 'non_empty_plates', 'plateNames':
                                 list(non_empty_plates)}, status=409)

    # TODO: Validate supplied cell line and drug IDs?

    # Add the cell lines
    wells_celllines_to_create = []
    well_drugs_to_create = []
    for i, well in enumerate(wells):
        # cell_line_id = None
        # if well['cellLine']:
        #     cell_line_id = cell_lines[well['cellLine']]
        # if not well['cellLine']:
        #     continue
        for p_id in plate_ids:
            wells_celllines_to_create.append(
                WellCellLine(plate_id=p_id,
                             well=i,
                             cell_line_id=well['cellLine']))

    try:
        with transaction.atomic():
            WellCellLine.objects.bulk_create(wells_celllines_to_create)
    except IntegrityError:
        cell_line_ids = [well['cellLine'] for well in wells]
        for cl_id in set(cell_line_ids):
            WellCellLine.objects.filter(
                plate_id=plate_id,
                well__in=np.where([this_id == cl_id for this_id in
                                   cell_line_ids])[0]).update(
                                                        cell_line_id=cl_id)

    # Since we don't know how many drugs in each well there were previously
    # in the case of an update, the easy
    # solution is just to delete/reinsert. The alternative would be select
    # for update, then delete/update/insert as appropriate, which would
    # probably be slower anyway due to the extra queries.
    if plate_id is not None:
        WellDrug.objects.filter(plate_id=plate_id).delete()

    for i, well in enumerate(wells):
        if well['drugs']:
            for drug_idx, drug_id in enumerate(well['drugs']):
                if drug_id is None:
                    continue
                try:
                    dose = well['doses'][drug_idx]
                except (TypeError, IndexError):
                    continue
                if dose is None:
                    continue
                for p_id in plate_ids:
                    well_drugs_to_create.append(WellDrug(
                        plate_id=p_id,
                        well=i,
                        drug_id=drug_id,
                        dose=dose
                    ))

    WellDrug.objects.bulk_create(well_drugs_to_create)

    if not plate_id:
        # If this was a template-based update...
        return JsonResponse({'success': True, 'templateAppliedTo': plate_ids})

    if plate_data.get('loadNext', None):
        next_plate_id = plate_data['loadNext']
        return ajax_load_plate(request, plate_id=next_plate_id,
                               extra_return_args={'savedPlateId': plate_id})
    else:
        return JsonResponse({'success': True, 'savedPlateId': plate_id})

    # TODO: Validate received PlateMap further?


@login_required
def ajax_load_plate(request, plate_id, extra_return_args=None):
    p = Plate.objects.get(id=plate_id,
                          dataset__owner_id=request.user.id)
    if not p:
        # TODO: Replace 404 with JSON
        raise Http404()

    cell_lines = WellCellLine.objects.filter(plate_id=plate_id).order_by(
        'well').values('cell_line_id')
    drugs = WellDrug.objects.filter(plate_id=plate_id).order_by('well').values(
        'well', 'drug_id', 'dose')

    wells = []
    for cl in range(p.num_wells):
        wells += [{'cellLine': cell_lines[cl]['cell_line_id'] if cell_lines
                else None,
                   'drugs': [], 'doses': []}]

    assert len(wells) == p.num_wells

    for dr in drugs:
        wells[dr['well']]['drugs'].append(dr['drug_id'])
        wells[dr['well']]['doses'].append(dr['dose'])

    plate = {'plateId': p.id,
             'plateFileId': p.plate_file_id,
             'numCols': p.width,
             'numRows': p.height,
             'wells': wells}

    return_dict = {'success': True, 'plateMap': plate}
    if extra_return_args is not None:
        return_dict.update(extra_return_args)

    return JsonResponse(return_dict)


@login_required
def ajax_create_dataset(request):
    name = request.POST.get('name')
    if not name:
        return HttpResponseBadRequest()
    dset = HTSDataset.objects.create(owner=request.user, name=name)
    return JsonResponse({'name': dset.name, 'id': dset.id})


@login_required
def ajax_create_cellline(request):
    name = request.POST.get('name')
    if not name:
        return HttpResponseBadRequest()
    CellLine.objects.get_or_create(name=name)
    cell_lines = CellLine.objects.order_by('name').values('id', 'name')
    return JsonResponse({'cellLines': list(cell_lines)})


@login_required
def ajax_create_drug(request):
    name = request.POST.get('name')
    if not name:
        return HttpResponseBadRequest()
    Drug.objects.get_or_create(name=name)
    drugs = Drug.objects.order_by('name').values('id', 'name')
    return JsonResponse({'drugs': list(drugs)})


@login_required
def ajax_get_datasets(request):

    datasets = HTSDataset.objects.filter(owner_id=request.user.id).values(
        'id', 'name', 'creation_date')

    response = {'data': list(datasets)}
    return JsonResponse(response)


class DatasetXlsxWriter(object):
    def __init__(self, request, dataset_id, prefix=None):
        try:
            self.dataset = HTSDataset.objects.filter(id=dataset_id,
                                                     owner=request.user)\
                .annotate(last_upload=Max('platefile__upload_date'),
                          last_annotated=Max('plate__last_annotated')).get()
        except HTSDataset.DoesNotExist:
            raise Http404()

        self.site = get_current_site(request)
        self.prefix = prefix
        self.request_user = request.user

    def __enter__(self):
        self.tempfile = tempfile.NamedTemporaryFile('wb',
                                                    dir=settings.DOWNLOADS_ROOT,
                                                    prefix=self.prefix,
                                                    delete=False)
        self.workbook = xlsxwriter.Workbook(self.tempfile)
        ws = self.workbook.add_worksheet('File Information')

        self.metadata = OrderedDict([
            ('Generated by', '{} ({})'.format(self.site.name,
                                              self.site.domain)),
            ('Software version', pyhts.__version__),
            ('Dataset created by', '{} (ID: {})'.format(
                             self.dataset.owner.email, self.dataset.owner.id)),
            ('Dataset created on', self.dataset.creation_date),
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
def xlsx_get_annotation_data(request, dataset_id):
    with DatasetXlsxWriter(request, dataset_id, prefix='xlsxannot-') as xlsx:
        tmp_filename = xlsx.tempfile.name
        output_filename = '{}-annotation.xlsx'.format(xlsx.dataset.name)

        plates = list(Plate.objects.filter(dataset_id=dataset_id)
                                   .order_by('id'))

        plate_ids = [p.id for p in plates]

        cell_lines = list(WellCellLine.objects.filter(plate_id__in=plate_ids)
                                              .order_by('plate_id', 'well'))

        drugs = list(WellDrug.objects.filter(plate_id__in=plate_ids)
                                     .order_by('plate_id', 'well'))

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
                    if cl.plate_id == p.id and cl.well == w_id:
                        ws.write(w_id+1, 1, cl.cell_line.name if cl.cell_line
                                 else '')
                        cl_pos += 1

                if dr_pos < len(drugs):
                    drugs_this_well = 0
                    while dr_pos < len(drugs) \
                            and drugs[dr_pos].plate_id == p.id \
                            and drugs[dr_pos].well == w_id:
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

    if settings.DEBUG:
        return serve(request, os.path.basename(tmp_filename),
                     os.path.dirname(tmp_filename))

    return nginx_file(tmp_filename,
                      rename_to=output_filename,
                      content_type='application/vnd.openxmlformats'
                                   '-officedocument.spreadsheetml.sheet')


@login_required
def xlsx_get_assay_data(request, dataset_id):
    with DatasetXlsxWriter(request, dataset_id, prefix='xlsxassay-') as xlsx:
        tmp_filename = xlsx.tempfile.name
        output_filename = '{}-assays.xlsx'.format(xlsx.dataset.name)

        assays = list(WellMeasurement.objects.filter(
            plate__dataset_id=dataset_id,
        ).order_by('plate_id', 'assay', 'timepoint', 'well').select_related())

        header = xlsx.styles['header']
        header_duration = xlsx.styles['header_duration']

        last_plate = None
        last_assay = None
        last_time = None
        last_time_col = 0

        for val in assays:

            if val.plate_id != last_plate:
                last_plate = val.plate_id
                last_assay = None
                last_time = None
                last_time_col = 0

            if val.assay != last_assay:
                last_assay = val.assay
                plate_name = '{}-{}'.format(val.plate.name, val.assay)
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

            ws.write(val.well + 1, 0, val.plate.well_id_to_name(val.well))
            ws.write(val.well + 1, last_time_col, val.value)

    if settings.DEBUG:
        return serve(request,
                     os.path.basename(tmp_filename),
                     os.path.dirname(tmp_filename))

    return nginx_file(tmp_filename, rename_to=output_filename,
                      content_type='application/vnd.openxmlformats'
                                   '-officedocument.spreadsheetml.sheet')


@login_required
def plate_designer(request, dataset_id):
    dataset = HTSDataset.objects.get(id=dataset_id, owner_id=request.user.id)
    if not dataset:
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
        'plate_sizes': plate_sizes,
        'plates': plates,
        'cell_lines': list(CellLine.objects.all().values('id', 'name')),
        'drugs': list(Drug.objects.all().values('id', 'name'))
    })
    return response


@login_required
def view_dataset(request, dataset_id):
    try:
        dataset = HTSDataset.objects.filter(id=dataset_id,
                                        owner_id=request.user.id)\
        .annotate(last_upload=Max('platefile__upload_date'),
                  last_annotated=Max('plate__last_annotated')).get()
    except HTSDataset.DoesNotExist:
        raise Http404()

    response = render(request, 'dataset.html', {'dataset': dataset})
    return response


@login_required
def ajax_get_dataset_groups(request, dataset_id):
    # TODO: Sanitise names for Javascript display
    cell_lines = WellCellLine.objects.filter(
        cell_line__isnull=False,
        plate__dataset_id=dataset_id,
        plate__dataset__owner_id=request.user.id
    ).values('cell_line_id', 'cell_line__name').distinct()

    drugs = WellDrug.objects.filter(
        drug__isnull=False,
        plate__dataset_id=dataset_id,
        plate__dataset__owner_id=request.user.id
    ).values('drug_id', 'drug__name').distinct()

    assays = WellMeasurement.objects.filter(
        plate__dataset_id=dataset_id,
        plate__dataset__owner_id=request.user.id
    ).values('assay').distinct()

    # TODO: Improve this handling of controls!
    KNOWN_CONTROLS = ['DMSO']

    drug_list = []
    controls_list = [{'id': None, 'name': 'None'}]
    for dr in drugs:
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


@login_required
def ajax_get_plot(request, plot_type):
    if plot_type != 'dose-response-times':
        # TODO: Return JsonError
        raise NotImplementedError()

    try:
        dataset_id = int(request.GET['datasetId'])
        cell_line_id = int(request.GET['cellLineId'])
        drug_id = int(request.GET['drugId'])
        assay = request.GET['assayId']
        control_id = request.GET['controlId']
        error_bars = request.GET['errorBars']
        yaxis = request.GET['logTransform']

        if control_id == 'null':
            control_id = None
        else:
            control_id = int(control_id)
    except (KeyError, ValueError):
        # TODO: Throw JsonError
        raise Http404()

    if error_bars == 'sd':
        aggregates = (np.mean, np.std)
    elif error_bars == 'range':
        aggregates = (np.mean, np.min, np.max)
    else:
        aggregates = (np.mean, )

    dr = df_dose_response(dataset_id=dataset_id, cell_line_id=cell_line_id,
                          drug_id=drug_id, assay=assay, control=control_id,
                          log2y=yaxis=='log2',
                          aggregates=aggregates)

    html = plot_dose_response(dr['df'],
                              title='Dose/response of {} on {} cells'.format(
                                dr['drug_name'], dr['cell_line_name']))

    return HttpResponse(html)


@login_required
def plots(request):
    dataset_id = 11

    cell_line_id = 7  # F36P
    drug_id = 3  # 52793 JAK1
    assay = 'BF'
    control_id = 6  # DMSO
    error_bars = 'sd'
    yaxis = 'log2'

    dr = df_dose_response(dataset_id=dataset_id, cell_line_id=cell_line_id,
                          drug_id=drug_id, assay=assay, control=control_id,
                          log2y=yaxis == 'log2',
                          aggregates=(np.mean, np.std))

    graphs = []
    for i in range(0, 4):
        html = plot_dose_response(dr['df'],
                                  title='Dose/response of {} on {} cells'.
                                  format(dr['drug_name'], dr['cell_line_name'])
                                  )

        graphs.append({'dataset_id': dataset_id,
                       'cell_line_id': cell_line_id,
                       'drug_id': drug_id,
                       'assay_id': assay,
                       'control_id': control_id,
                       'error_bars': error_bars,
                       'log_transform': yaxis,
                       'html': html})

    return render(request, 'plots.html', {'graphs': graphs})
