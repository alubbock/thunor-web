from django.shortcuts import render, Http404
from django.template.loader import get_template
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib.auth.models import Group
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Max
from thunorweb.models import HTSDataset, PlateFile, Plate, \
    CellLineTag, DrugTag
from django.urls import reverse
from thunorweb.tasks import precalculate_dip_rates, precalculate_viability, \
    dataset_groupings, precalculate_dip_curves, rename_dataset_in_cache
from thunorweb.plate_parsers import PlateFileParser
from django.utils import timezone
from django.conf import settings
from guardian.shortcuts import get_objects_for_group, get_perms, \
    get_groups_with_perms, assign_perm, remove_perm
from django.contrib.contenttypes.models import ContentType
from thunorweb.views import login_required_unless_public, _assert_has_perm
import logging
from thunorweb.views.tags import TAG_EVERYTHING_ELSE

logger = logging.getLogger(__name__)


LICENSE_UNSIGNED = 'The dataset "{}" has usage terms which much be accepted ' \
                   'before it can be accessed. Please access the dataset ' \
                   'from the home page first to see and accept the terms.'


def license_accepted(request, dataset):
    return dataset.license_text is None or \
           dataset.owner_id == request.user.id or \
           f'dataset_{dataset.id}_lics_agree' in request.session


@login_required_unless_public
@ensure_csrf_cookie
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
        if not settings.LOGIN_REQUIRED and not request.user.is_authenticated:
            perms = get_perms(Group.objects.get(name='Public'), dataset)
        else:
            perms = get_perms(request.user, dataset)
        if not (set(perms_base) & set(perms)):
            raise Http404()

    dataset.single_timepoint = dataset_groupings(dataset)['singleTimepoint']
    dataset.license_accepted = license_accepted(request, dataset)

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

    available_perms = HTSDataset.view_dataset_permissions()

    all_groups = request.user.groups.all()
    groups_with_perms = get_groups_with_perms(dataset, True)

    group_perms = {}
    for gr in all_groups:
        matching_gr_perms = groups_with_perms.get(gr, [])
        group_perms[gr] = [(perm, perm in matching_gr_perms) for perm in
                           available_perms]

    response = render(request, 'dataset-permissions.html', {
        'dataset': dataset, 'available_perms': available_perms,
         'group_perms': group_perms})

    return response


@login_required_unless_public
def accept_license(request, dataset_id):
    try:
        dataset = HTSDataset.objects.get(id=dataset_id,
                                         deleted_date=None)
    except HTSDataset.DoesNotExist:
        raise Http404()

    perms_base = dataset.view_dataset_permission_names()

    if dataset.license_text is None or dataset.owner_id == request.user.id:
        # No license, or owner has already accepted license
        return JsonResponse({'success': True})
    else:
        if not settings.LOGIN_REQUIRED and not request.user.is_authenticated:
            perms = get_perms(Group.objects.get(name='Public'), dataset)
        else:
            perms = get_perms(request.user, dataset)
        if not (set(perms_base) & set(perms)):
            raise Http404()

    # Store the license acceptance
    request.session[f'dataset_{dataset.id}_lics_agree'] = \
        timezone.now().isoformat()

    return JsonResponse({'success': True})


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


def _get_drugtag_permfilter(request):
    if request.user.is_authenticated:
        # These queries assume we only have one permission (view) for tags
        return Q(owner=request.user) | Q(
            drugtaggroupobjectpermission__group__user=request.user
        )
    else:
        return Q(drugtaggroupobjectpermission__group__name='Public')


def _get_celllinetag_permfilter(request):
    if request.user.is_authenticated:
        # These queries assume we only have one permission (view) for tags
        return Q(owner=request.user) | Q(
            celllinetaggroupobjectpermission__group__user=request.user
        )
    else:
        return Q(celllinetaggroupobjectpermission__group__name='Public')


def _get_tags(request, cell_line_ids, drug_ids):
    ct_perm_filter = _get_celllinetag_permfilter(request)
    dt_perm_filter = _get_drugtag_permfilter(request)

    cell_line_tags = CellLineTag.objects.filter(ct_perm_filter).filter(
        cell_lines__id__in=cell_line_ids
    ).distinct().order_by('tag_category', 'tag_name')

    drug_tags = DrugTag.objects.filter(dt_perm_filter).filter(
        drugs__id__in=drug_ids
    ).distinct().order_by('tag_category', 'tag_name')

    return cell_line_tags, drug_tags


@login_required_unless_public
def ajax_get_dataset_groupings(request, dataset_id, dataset2_id=None):
    dataset_ids = [dataset_id]
    if dataset2_id is not None:
        dataset_ids.append(dataset2_id)

    plates = Plate.objects.filter(
        dataset__in=dataset_ids).select_related('dataset')

    datasets = set([p.dataset for p in plates])

    if len(datasets) == 0:
        # Maybe we just have no plates, get datasets to check permissions
        datasets = HTSDataset.objects.filter(id__in=dataset_ids)
        if len(datasets) == 0:
            raise Http404()
    elif len(datasets) != len(dataset_ids):
        raise Http404()

    for dataset in datasets:
        _assert_has_perm(request, dataset, 'view_plots')
        if not license_accepted(request, dataset):
            return HttpResponse(LICENSE_UNSIGNED.format(dataset.name),
                                status=400)

    if len(plates) == 0:
        return HttpResponse(
            'This dataset has no plate files. Data will need to be added '
            'before plots can be used on this dataset.', status=400)

    groupings_dict = dataset_groupings(list(datasets))

    cell_line_ids = [cl['id'] for cl in groupings_dict['cellLines']]
    drug_ids = []
    for dr in groupings_dict['drugs']:
        drug_ids.append(dr['id']) if isinstance(dr['id'], int) else \
            drug_ids.extend(dr['id'])

    cell_line_tags, drug_tags = _get_tags(request, cell_line_ids, drug_ids)

    groupings_dict['drugTags'] = []
    groupings_dict['cellLineTags'] = []

    last_cat = None
    append_to = groupings_dict['drugTags']
    for tag in drug_tags:
        if tag.tag_category != last_cat:
            groupings_dict['drugTags'].append({'optgroup': tag.tag_category,
                                               'options': []})
            last_cat = tag.tag_category
            append_to = groupings_dict['drugTags'][-1]['options']
        append_to.append(
            {'id': tag.id,
             'name': tag.tag_name}
        )

    special_tags = {'optgroup': 'Special Tags',
                    'options': [{'id': TAG_EVERYTHING_ELSE,
                                 'name': 'Everything else'}]}
    groupings_dict['drugTags'].append(special_tags)

    last_cat = None
    append_to = groupings_dict['cellLineTags']
    for tag in cell_line_tags:
        if tag.tag_category != last_cat:
            groupings_dict['cellLineTags'].append(
                {'optgroup': tag.tag_category, 'options': []})
            last_cat = tag.tag_category
            append_to = groupings_dict['cellLineTags'][-1]['options']
        append_to.append(
            {'id': tag.id,
             'name': tag.tag_name}
        )

    groupings_dict['cellLineTags'].append(special_tags)

    if groupings_dict['singleTimepoint'] is False:
        groupings_dict['plates'] = [{'id': p.id, 'name': p.name}
                                    for p in plates]
    else:
        groupings_dict['plates'] = []

    return JsonResponse(groupings_dict)


def ajax_get_datasets(request):
    if not request.user.is_authenticated:
        return JsonResponse({}, status=401)

    datasets = HTSDataset.objects.filter(owner_id=request.user.id,
                                         deleted_date=None).values(
        'id', 'name', 'creation_date')

    datasets = [{
        'id': d['id'],
        'name': d['name'],
        'ownerEmail': request.user.email,
        'creationDate': d['creation_date']}
        for d in datasets]

    return JsonResponse({'data': datasets})


def ajax_get_datasets_group(request, group_id):
    if group_id == 'Public' and (request.user.is_authenticated or
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
        ).filter(deleted_date=None).values('id', 'name', 'creation_date',
                                           'owner__email')
    except ContentType.DoesNotExist:
        return JsonResponse({'data': list()})

    datasets = [{
        'id': d['id'],
        'name': d['name'],
        'ownerEmail': d['owner__email'],
        'creationDate': d['creation_date']}
        for d in datasets]

    return JsonResponse({'data': datasets})


def ajax_create_dataset(request):
    if not request.user.is_authenticated:
        return JsonResponse({}, status=401)

    name = request.POST.get('name')
    if not name:
        return HttpResponseBadRequest()
    dset = HTSDataset.objects.create(owner=request.user, name=name)
    return JsonResponse({'name': dset.name, 'id': dset.id})


def ajax_rename_dataset(request):
    if not request.user.is_authenticated:
        return JsonResponse({}, status=401)

    try:
        dataset_id = request.POST['datasetId']
    except KeyError:
        return JsonResponse({'error': 'datasetId is a required field'},
                            status=400)
    try:
        dataset_name = request.POST['datasetName']
    except KeyError:
        return JsonResponse({'error': 'datasetName is a required field'},
                            status=400)

    n_updated = HTSDataset.objects.filter(
        id=dataset_id, owner_id=request.user.id).update(
        name=dataset_name
    )

    if n_updated < 1:
        raise Http404()

    rename_dataset_in_cache(dataset_id, dataset_name)

    return JsonResponse({'success': True,
                         'datasetId': dataset_id,
                         'datasetName': dataset_name})


def ajax_delete_dataset(request):
    if not request.user.is_authenticated:
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
    if not request.user.is_authenticated:
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
    if not request.user.is_authenticated:
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
        precalculate_dip_curves(dataset)
        precalculate_viability(dataset)
        dataset_groupings(dataset, regenerate_cache=True)

    response = {
        'initialPreview': initial_previews,
        'initialPreviewConfig': initial_preview_config}

    if errors:
        response['error'] = '<br>'.join(errors.values())
        response['errorkeys'] = list(errors.keys())

    return JsonResponse(response)
