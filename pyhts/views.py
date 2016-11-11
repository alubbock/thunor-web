from django.shortcuts import render, redirect, Http404
from django.template.response import TemplateResponse
from django.contrib import auth
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from .forms import CentredAuthForm, PlateFileForm
from django.views.generic.edit import FormView
from django.http import JsonResponse, HttpResponseBadRequest
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.db.models import F
from .models import HTSDataset, PlateFile, Plate, CellLine, Drug, PlateMap, \
    WellCellLine, WellMeasurement, WellDrug
import json
from helpers import guess_timepoint_hrs
from plate_parsers import parse_platefile_readerX
import numpy as np

HOURS_TO_SECONDS = 3600


def _handle_login(request):
    if request.method == 'POST':
        form = CentredAuthForm(data=request.POST)
        if form.is_valid():
            auth.login(request, form.get_user())
            return redirect('pyhts:home')
    else:
        form = CentredAuthForm()
    return render(request, 'registration/login.html', {'form': form})


def parse_platefile(pf):
    # TODO: Ensure file isn't too big, check filetype etc.
    file_timepoint_guess = guess_timepoint_hrs(pf.name)

    pd = pf.read()
    return parse_platefile_readerX(pd, quick_parse=False,
                                   file_timepoint_guess_hrs=file_timepoint_guess)


def home(request):
    if not request.user.is_authenticated:
        return _handle_login(request)

    return render(request, 'home.html')


def logout(request):
    auth.logout(request)
    return redirect('pyhts:home')


class PlateUpload(FormView):
    form_class = PlateFileForm
    template_name = 'plate_upload.html'

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super(PlateUpload, self).dispatch(*args, **kwargs)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        from datetime import datetime

        print('start '+str(datetime.now()))

        form_class = self.get_form_class()
        form = self.get_form(form_class)
        dataset_id = request.POST.get('dataset_id')
        files = request.FILES.getlist('file_field')
        if form.is_valid():
            response = {'success': False}

            dataset = HTSDataset(owner=request.user, id=dataset_id)
            if not dataset:
                form.add_error('dataset_id', 'Dataset %s does not exist or '
                                             'you do not have access' %
                                             dataset_id)
                return JsonResponse({'success': False, 'errors':
                                    form.errors.as_json()})

            file_status = {}
            for f in files:
                    plates = parse_platefile(f)
                    tpf = PlateFile(dataset=dataset, file=f)
                    tpf.save()
                    well_measurements = []
                    for p in plates:
                        print('processing plate '+p['name'] + ' ' +
                              str(datetime.now()))
                        plate = Plate(plate_file=tpf,
                                      name=p['name'],
                                      width=p['well_cols'],
                                      height=p['well_rows'])
                        plate.save()
                        p['id'] = plate.id
                        print(plate.id)

                        # Create wells
                        for assay_name, values in p['well_values'].items():
                            for pos, wv in enumerate(values):
                                well_measurements.append(WellMeasurement(
                                    plate_id=plate.id,
                                    well=pos,
                                    assay=assay_name,
                                    value=wv
                                ))

                        del p['well_values']

                    WellMeasurement.objects.bulk_create(well_measurements)

                    response['success'] = True
                    file_status[tpf.id] = {'success': True,
                                           'name': f.name,
                                           'message': '{} plates detected'
                                                      .format(len(plates)),
                                           'plates': plates
                                           }
                # except ValueError as ve:
                #     file_status['_failed'] = {'success': False,
                #                               'name': f.name,
                #                               'message': ve.message}
            response['files'] = file_status
            print('returning response ' + str(datetime.now()))
            return JsonResponse(response)
        else:
            return JsonResponse({'success': False, 'errors':
                                form.errors.as_json()})


# @login_required
# def ajax_get_plates(request, file_id):
#     pf = Plate.objects.filter(plate_file_id=file_id,
#                               plate_file__dataset__owner_id=request.user.id)
#     return JsonResponse({'plates': list(pf.values('id', 'name'))})


@login_required
def ajax_table_view(request):
    plate_data = json.loads(request.body)
    well_iterator = PlateMap(width=int(plate_data['numCols']),
                             height=int(plate_data['numRows'])).well_iterator()
    wells = plate_data['wells']

    for well in well_iterator:
        wells[well['well']]['wellName'] = '{}{:02d}'.format(well['row'],
                                                            well['col'])

    return TemplateResponse(request, 'plate_table_view.html',
                            {'wells': wells})


@login_required
@transaction.atomic
def ajax_save_plate(request):
    plate_data = json.loads(request.body)
    plate_id = int(plate_data['plateId'])
    wells = plate_data['wells']

    # Check permissions
    try:
        p = Plate.objects.get(id=plate_id,
                          plate_file__dataset__owner_id=request.user.id)
    except ObjectDoesNotExist:
        return Http404()

    # Get the used cell lines and drugs
    # TODO: Maybe add a permission model to these
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
        (unq_cl, cl_which) = np.unique(cell_line_ids, return_inverse=True)
        for idx, cl_id in enumerate(unq_cl):
            WellCellLine.objects.filter(
                plate_id=plate_id,
                well__in=np.where(cl_which == idx)[0]).update(cell_line_id=
                                                                 cl_id)

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
        get_plate_names = plate_data.get('getPlateNames', False)
        return ajax_load_plate(request, plate_id=next_plate_id,
                               get_plate_names=get_plate_names)
    else:
        return JsonResponse({'success': True})

    # TODO: Validate received PlateMap


@login_required
def ajax_load_plate(request, plate_id, get_plate_names=False):
    if 'getPlateNames' in request.GET:
        get_plate_names = True
    p = Plate.objects.get(id=plate_id,
                          plate_file__dataset__owner_id=request.user.id)
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

    if get_plate_names:
        pf = Plate.objects.filter(plate_file_id=p.plate_file_id)
        return_dict['plateNames'] = list(pf.values('id', 'name'))

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
@transaction.atomic
def ajax_set_timepoints(request):
    # TODO: Respond with appropriate JSON responses under error conditions
    try:
        HTSDataset.objects.get(id=request.POST.get('dataset-id', None),
                                  owner_id=request.user.id)
    except ObjectDoesNotExist:
        return Http404()

    plate_prefix = 'plate_'

    plates_to_update = {key[len(plate_prefix):]: value for (key, value) in
                        request.POST.items()
                        if key.startswith(plate_prefix)}

    # count = Plate.objects.filter(id__in=plates_to_update.keys(),
    #                      plate_file__dataset__owner_id=request.user.id
    #                      ).count()
    #
    # if count < len(plates_to_update):
    #     # Some of those plates don't exist or are owned by a different user
    #     return Http404()

    for pl_id, pl_timepoint in plates_to_update.items():
        updated = Plate.objects.filter(id=pl_id,
                          plate_file__dataset__owner_id=request.user.id
                          ).update(timepoint_secs=float(pl_timepoint) *
                                                  HOURS_TO_SECONDS)
        if not updated:
            return Http404()

    return JsonResponse({'success': True})


@login_required
def plate_designer(request, dataset_id):
    dset = HTSDataset.objects.get(id=dataset_id, owner_id=request.user.id)
    if not dset:
        raise Http404()
    dataset_name = dset.name

    pf = list(PlateFile.objects.filter(dataset_id=dataset_id,
                                       dataset__owner_id=request.user.id,
                                       process_date=None).order_by('id'))

    plates = list(Plate.objects.filter(plate_file__dataset_id=dataset_id).
                  order_by('plate_file_id', 'id'))

    all_plates = [{'id': p.id, 'name': p.name,
                   'plate_file_id': p.plate_file_id} for p in plates]

    # build a list of plates nested by plate file
    plates_nested = []
    plates_level = []
    last_platefile = all_plates[0]['plate_file_id']
    for i, pl in enumerate(all_plates):
        if pl['plate_file_id'] != last_platefile:
            last_platefile = pl['plate_file_id']
            plates_nested.append(plates_level)
            plates_level = []
        plates_level.append(pl)
    # final append
    plates_nested.append(plates_level)

    current_plate = plates[0]

    response = TemplateResponse(request, 'plate_designer.html', {
        'dataset_id': dataset_id,
        'dataset_name': dataset_name,
        'current_plate': current_plate,
        'plate_files': pf,
        'plates': all_plates,
        'plates_nested': plates_nested,
        'cell_lines': list(CellLine.objects.all().values('id', 'name')),
        'drugs': list(Drug.objects.all().values('id', 'name'))
    })
    return response
