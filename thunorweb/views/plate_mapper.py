from django.shortcuts import render, Http404
from django.template.response import TemplateResponse
from django.http import JsonResponse, HttpResponseBadRequest
from django.db import transaction
from django.db.models import Q, Count
from thunorweb.models import HTSDataset, Plate, CellLine, Drug, \
    Well, WellDrug, WellStatistic
import json
from thunor.io import PlateData, STANDARD_PLATE_SIZES, PlateMap
from thunorweb.tasks import precalculate_viability, \
    dataset_groupings, precalculate_dip_curves
import numpy as np
import math
from django.utils import timezone
from django.conf import settings
from collections import defaultdict, namedtuple
from thunorweb.helpers import AutoExtendList
from thunorweb.views import login_required_unless_public, _assert_has_perm


@login_required_unless_public
def plate_mapper(request, dataset_id, num_wells=None):
    editable = True
    plate_sizes = set()
    plate_size = namedtuple('plate_size', 'numCols numRows numWells')
    if dataset_id is None:
        if num_wells is None:
            return render(request, 'plate_designer_choose_size.html')
        num_wells = int(num_wells)
        if num_wells not in STANDARD_PLATE_SIZES:
            raise Http404()
        width, height = PlateMap.plate_size_from_num_wells(num_wells)
        plates = [Plate(id='MASTER', width=width, height=height)]
        dataset = None
        plate_sizes.add(plate_size(width, height, num_wells))
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
            plate_sizes.add(plate_size(plate.width, plate.height,
                                       plate.num_wells))

        plate_sizes = sorted(plate_sizes, key=lambda ps: ps.numWells)

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


@transaction.atomic
def ajax_save_plate(request):
    if not request.user.is_authenticated():
        return JsonResponse({}, status=401)

    plate_data = json.loads(request.body.decode(request.encoding or 'utf-8'))

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
                             dataset__deleted_date=None
                             ).select_related('dataset')

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
        existing_wells = set(Well.objects.filter(
            plate_id__in=plate_ids).values_list('plate_id', 'well_num'))
        # Update existing wells
        for cl_id in set(cell_line_ids):
            Well.objects.filter(
                plate_id__in=plate_ids,
                well_num__in=np.where([this_id == cl_id for this_id in
                                   cell_line_ids])[0]).update(
                                                        cell_line_id=cl_id)
        # Insert new wells
        wells_to_insert = []
        for plate in plate_ids:
            for well_num, cell_line_id in enumerate(cell_line_ids):
                if not (plate, well_num) in existing_wells:
                    wells_to_insert.append(Well(
                        well_num=well_num,
                        plate_id=plate,
                        cell_line_id=cell_line_id
                    ))
        Well.objects.bulk_create(wells_to_insert)

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

    dataset = pl_objs[0].dataset
    # Update modified_date
    dataset.save()

    # TODO: Hand off for asynchronous processing with celery
    dataset_groupings(dataset, regenerate_cache=True)
    precalculate_dip_curves(dataset)
    precalculate_viability(dataset)

    if apply_mode != 'normal':
        # If this was a template-based update...
        return JsonResponse({'success': True, 'templateAppliedTo': plate_ids})

    if plate_data.get('loadNext', None):
        next_plate_id = plate_data['loadNext']
        return ajax_load_plate(request, plate_id=next_plate_id,
                               extra_return_args={'savedPlateId': plate_id})
    else:
        return JsonResponse({'success': True, 'savedPlateId': plate_id})


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
