from django.shortcuts import render
from django.http import JsonResponse
from django.db.models import Q, F
from thunorweb.models import CellLine, Drug, CellLineTag, DrugTag
from thunorweb.views import login_required_unless_public
import logging
import pandas as pd
import collections

logger = logging.getLogger(__name__)


@login_required_unless_public
def tag_editor(request, tag_type=None, tag_public=False):
    if request.user.is_authenticated() and not tag_public:
        tag_owner_filter = Q(owner=request.user)
    else:
        tag_owner_filter = Q(owner=None)

    if tag_type == 'cell_lines':
        entity_type = 'Cell Line'
        entity_type_var = 'cl'
        entity_options = {c.id: c for c in CellLine.objects.all().order_by(
            'name')}
        tag_list = CellLineTag.objects.filter(tag_owner_filter).order_by(
            'tag_category', 'tag_name', 'cell_lines__name').values_list(
            'tag_category', 'tag_name', 'cell_lines__id', 'cell_lines__name',
            'id')
    elif tag_type == 'drugs':
        entity_type = 'Drug'
        entity_type_var = 'drug'
        entity_options = {d.id: d for d in Drug.objects.all().order_by('name')}
        tag_list = DrugTag.objects.filter(tag_owner_filter).order_by(
            'tag_category', 'tag_name').values_list(
            'tag_category', 'tag_name', 'drugs__id', 'drugs__name', 'id')
    else:
        return render(request, "tags.html")

    tag_dict_selected = collections.defaultdict(dict)
    tag_ids = collections.defaultdict(list)
    for tag in tag_list:
        el = tag_dict_selected[tag[0]].setdefault((tag[4], tag[1]), [])
        if tag[3]:
            el.append(tag[3])
        tag_ids[tag[4]].append(tag[2])

    return render(request, "tag_editor.html",
                  {'entity_type': entity_type,
                   'entity_type_var': entity_type_var,
                   'tag_type': tag_type,
                   'entities': entity_options,
                   'tags': dict(tag_dict_selected),
                   'public': tag_public,
                   'tags_ids': tag_ids
                   }
                  )


def ajax_create_tag(request):
    if not request.user.is_authenticated():
        return JsonResponse({}, status=401)

    try:
        tag_name = request.POST['tagName']
        tag_category = request.POST['tagCategory']
        tag_type = request.POST['tagType']
    except KeyError:
        return JsonResponse({'error': 'Form not properly formatted'},
                            status=400)

    if tag_type not in ('cl', 'drug'):
        return JsonResponse({'error': 'Tag type not recongised'}, stauts=400)

    tag_name = tag_name.strip()
    if tag_name == '':
        return JsonResponse({'error': 'Tag name must contain non-whitespace '
                                      'characters'}, status=400)

    tag_category = tag_category.strip()

    tag_cls = DrugTag if tag_type == 'drug' else CellLineTag

    tag = tag_cls.objects.create(
        owner=request.user,
        tag_name=tag_name,
        tag_category=tag_category
    )

    return JsonResponse({
        'success': True,
        'tagId': tag.id,
        'tagName': tag.tag_name,
        'tagCategory': tag.tag_category,
        'tagType': tag_type
    })


def ajax_rename_tag(request):
    if not request.user.is_authenticated():
        return JsonResponse({}, status=401)

    try:
        tag_id = request.POST.get('tagId')
        tag_name = request.POST.get('tagName')
        tag_category = request.POST.get('tagCategory', '')
        tag_type = request.POST.get('tagType')
        if tag_type not in ('cl', 'drug'):
            raise ValueError
    except (KeyError, ValueError):
        return JsonResponse({'error': 'Form not properly formatted'},
                            status=400)

    tag_cls = DrugTag if tag_type == 'drug' else CellLineTag

    perm_query = Q(owner=request.user)

    if request.user.is_superuser:
        perm_query |= Q(owner=None)

    n_updated = tag_cls.objects.filter(perm_query).filter(
        id=tag_id).update(tag_name=tag_name, tag_category=tag_category)

    if n_updated == 0:
        return JsonResponse({'error': 'Tag not found'}, status=404)

    return JsonResponse({'success': True})


def ajax_delete_tag(request):
    if not request.user.is_authenticated():
        return JsonResponse({}, status=401)

    try:
        tag_id = request.POST['tagId']
        tag_type = request.POST.get('tagType')
        if tag_type not in ('cl', 'drug'):
            raise ValueError
    except (KeyError, ValueError):
        return JsonResponse({'error': 'Form not properly formatted'},
                            status=400)

    tag_cls = DrugTag if tag_type == 'drug' else CellLineTag

    perm_query = Q(owner=request.user)

    if request.user.is_superuser:
        perm_query |= Q(owner=None)

    n_deleted, _ = tag_cls.objects.filter(perm_query).filter(
        id=tag_id).delete()

    if n_deleted == 0:
        return JsonResponse({'error': 'Tag requested not found'}, status=404)

    return JsonResponse({'success': True, 'tagId': tag_id})


def ajax_upload_tagfile(request, tag_type):
    assert tag_type in ('cell_lines', 'drugs')

    if not request.user.is_authenticated():
        return JsonResponse({'error': 'Not logged in'}, status=401)

    files = request.FILES.getlist('tagfiles[]')
    if len(files) == 0:
        return JsonResponse({'error': 'No files uploaded'}, status=400)

    EntityClass = CellLine if tag_type == 'cell_lines' else Drug
    TagClass = CellLineTag if tag_type == 'cell_lines' else DrugTag
    ent_col = 'cell_line' if tag_type == 'cell_lines' else 'drug'
    ent_name = 'Cell lines' if tag_type == 'cell_lines' else 'Drugs'

    ent_mapping = {ent.name.lower(): ent.id for ent in
                   EntityClass.objects.all()}

    for file in files:
        if file.name.endswith('.txt'):
            sep = '\t'
        elif file.name.endswith('.csv'):
            sep = ','
        else:
            return JsonResponse({'error', 'File name must end with .txt'
                                          '(Tab separated) or .csv '
                                          '(Comma separated)'}, status=400)

        try:
            csv = pd.read_csv(file, sep=sep)
        except:
            return JsonResponse({
                'error': 'Could not read file. Please ensure file is comma '
                         'separated (with extension .csv) or tab separated ('
                         'with extension .txt)'
             }, status=400)

        if 'tag_name' not in csv.columns:
            return JsonResponse({'error': 'Column tag_name not found'},
                                status=400)
        if 'tag_category' not in csv.columns:
            return JsonResponse({'error': 'Column tag_category not found'},
                                status=400)
        if tag_type == 'drugs' and 'drug' not in csv.columns:
            return JsonResponse({'error': 'Column drug not found'},
                                status=400)
        if tag_type == 'cell_lines' and 'cell_line' not in csv.columns:
            return JsonResponse({'error': 'Column cell_line not found'},
                                status=400)

        csv['ent_lower'] = csv[ent_col].str.lower()

        csv = csv[['tag_name', 'tag_category', 'ent_lower']]
        duplicates = csv.duplicated()
        if duplicates.any():
            duplicates = csv[duplicates].iloc[0, :]
            dup_str = ','.join([duplicates['tag_category'], duplicates[
                'tag_name'], duplicates['ent_lower']])
            return JsonResponse({'error': 'File contains duplicates, '
                                          'e.g. {}'.format(dup_str)})

        missing_ents = set(csv['ent_lower']).difference(ent_mapping.keys())
        if missing_ents:
            return JsonResponse({
                'error': '{} not found (shown in lower case): {}'.format(
                    ent_name, missing_ents)})

        grpby = csv.groupby(['tag_category', 'tag_name'])
        tags = []
        for grp, _ in grpby:
            tags.append(TagClass(
                tag_category=grp[0],
                tag_name=grp[1],
                owner_id=request.user.id
            ))
        TagClass.objects.bulk_create(tags)

        for idx, x in enumerate(grpby):
            grp, entities = x

            tag = tags[idx]
            entity_ids = [ent_mapping[e] for e in entities['ent_lower']]

            if tag_type == 'drugs':
                tag.drugs.set(entity_ids)
            else:
                tag.cell_lines.set(entity_ids)

    return JsonResponse({'success': True})


def ajax_assign_tag(request):
    if not request.user.is_authenticated():
        return JsonResponse({}, status=401)

    try:
        tag_id = request.POST.get('tagId')
        tag_type = request.POST.get('tagType')
        if tag_type not in ('cl', 'drug'):
            raise ValueError('Unknown tag type')
        entity_ids = [int(e_id) for e_id in request.POST.getlist('entityId')]
    except (KeyError, ValueError):
        return JsonResponse({'error': 'Form not properly formatted'},
                            status=400)

    tag_cls = DrugTag if tag_type == 'drug' else CellLineTag

    perm_query = Q(owner=request.user)

    if request.user.is_superuser:
        perm_query |= Q(owner=None)

    try:
        tag = tag_cls.objects.filter(perm_query).get(id=tag_id)
    except tag_cls.DoesNotExist:
        return JsonResponse({'error': 'Requested tag does not exist'},
                            status=404)

    if tag_type == 'drug':
        tag.drugs.set(entity_ids)
    else:
        tag.cell_lines.set(entity_ids)

    logger.info('Tag modified', extra={'request': request})

    return JsonResponse({
        'success': True,
        'tagId': tag_id,
        'entityIds': entity_ids
    })
