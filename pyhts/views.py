from django.shortcuts import render, redirect, Http404
from django.template.response import TemplateResponse
from django.template.loader import get_template
from django.contrib import auth
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from .forms import CentredAuthForm
from django.views.generic.edit import FormView
from django.http import JsonResponse, HttpResponseBadRequest, \
    HttpResponseServerError, HttpResponseNotFound
from django.core.exceptions import ObjectDoesNotExist
from django.db.utils import IntegrityError
from django.db import transaction
from django.db.models import F
from .models import HTSDataset, PlateFile, Plate, CellLine, Drug, \
    WellCellLine, WellMeasurement, WellDrug
import json
from .plate_parsers import PlateFileParser, PlateFileParseException
import numpy as np
from datetime import timedelta
from django.utils import timezone
from django.utils.encoding import smart_text
from operator import itemgetter
from django.shortcuts import render_to_response
from django.template import RequestContext
import logging

logger = logging.getLogger(__name__)

HOURS_TO_SECONDS = 3600


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


# @login_required
# def ajax_get_plates(request, file_id):
#     pf = Plate.objects.filter(plate_file_id=file_id,
#                               plate_file__dataset__owner_id=request.user.id)
#     return JsonResponse({'plates': list(pf.values('id', 'name'))})


# @login_required
# def ajax_table_view(request):
#     plate_data = json.loads(request.body)
#     well_iterator = PlateMap(width=int(plate_data['numCols']),
#                              height=int(plate_data['numRows'])).well_iterator()
#     wells = plate_data['wells']
#
#     for well in well_iterator:
#         wells[well['well']]['wellName'] = '{}{:02d}'.format(well['row'],
#                                                             well['col'])
#
#     return TemplateResponse(request, 'plate_table_view.html',
#                             {'wells': wells})

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
    plate_id = int(plate_data['plateId'])
    wells = plate_data['wells']

    # Check permissions
    n_updated = Plate.objects.filter(id=plate_id,
                             dataset__owner_id=request.user.id).update(
        last_annotated=timezone.now())
    if n_updated != 1:
        #TODO: This should return a better error
        raise Http404()

    # Get the used cell lines and drugs
    # TODO: Validate supplied cell line and drug IDs?
    # cell_line_ids = set([well['cellLine'] for well in wells])
    # cell_lines = dict(CellLine.objects.filter(
    #     id__in=cell_line_ids).values_list(
    #     'name', 'id'))
    #
    # drug_ids = set()
    # for well in wells:
    #     if well['drugs'] is None:
    #         continue
    #     for drug in well['drugs']:
    #         drug_ids.add(drug)
    # drugs = dict(Drug.objects.filter(
    #     ids__in=drug_ids).values_list(
    #     'name', 'id'))

    # Add the cell lines
    wells_celllines_to_create = []
    well_drugs_to_create = []
    for i, well in enumerate(wells):
        # cell_line_id = None
        # if well['cellLine']:
        #     cell_line_id = cell_lines[well['cellLine']]
        # if not well['cellLine']:
        #     continue
        wells_celllines_to_create.append(
            WellCellLine(plate_id=plate_id,
                         well=i,
                         cell_line_id=well['cellLine']))

    try:
        with transaction.atomic():
            WellCellLine.objects.bulk_create(wells_celllines_to_create)
    except IntegrityError:
        # Do update instead
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
    WellDrug.objects.filter(plate_id=plate_id).delete()

    for i, well in enumerate(wells):
        if well['drugs']:
            for drug_idx, drug_id in enumerate(well['drugs']):
                if not drug_id:
                    continue
                try:
                    dose = well['doses'][drug_idx]
                except (TypeError, IndexError):
                    continue
                if not dose:
                    continue
                well_drugs_to_create.append(WellDrug(
                    plate_id=plate_id,
                    well=i,
                    drug_id=drug_id,
                    dose=dose
                ))

    WellDrug.objects.bulk_create(well_drugs_to_create)

    if plate_data.get('loadNext', None):
        next_plate_id = plate_data['loadNext']
        return ajax_load_plate(request, plate_id=next_plate_id,
                               saved_plate_id=plate_id)
    else:
        return JsonResponse({'success': True, 'savedPlateId': plate_id})

    # TODO: Validate received PlateMap


@login_required
def ajax_load_plate(request, plate_id, saved_plate_id=None):
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

    if saved_plate_id:
        return_dict['savedPlateId'] = saved_plate_id

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
    #plates = Plate.objects.filter(
    # dataset__owner_id=request.user.id).select_related()

    #datasets = set([p.dataset for p in plates])

    datasets = HTSDataset.objects.filter(owner_id=request.user.id).all()
    # plate_set = datasets.plate_set.all()
    # platefiles = datasets.platefile_set.all().count()

    response = {'data': [[d.name, d.creation_date] for d in datasets]}
    return JsonResponse(response)


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
