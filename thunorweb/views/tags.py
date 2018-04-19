from django.shortcuts import render
from django.http import JsonResponse
from django.db.models import Q, F
from thunorweb.models import CellLine, Drug, CellLineTag, DrugTag
from thunorweb.views import login_required_unless_public
import logging
import pandas as pd

logger = logging.getLogger(__name__)


@login_required_unless_public
def tag_editor(request, tag_type=None, tag_public=False):
    if request.user.is_authenticated() and not tag_public:
        tag_owner_filter = Q(owner=request.user)
    else:
        tag_owner_filter = Q(owner=None)

    tag_dict_selected = {}
    if tag_type == 'cell_lines':
        entity_type = 'Cell Line'
        entity_type_var = 'cl'
        entity_options = {c.id: c for c in CellLine.objects.all().order_by(
            'name')}
        tag_list = CellLineTag.objects.filter(tag_owner_filter).order_by(
                F('owner_id').asc(nulls_last=True), 'tag_category', 'tag_name',
                'cell_line__name')
        for tag in tag_list:
            tag_dict_selected.setdefault(tag.tag_category, {}).setdefault(
                tag.tag_name, []).append(entity_options[tag.cell_line_id])
    elif tag_type == 'drugs':
        entity_type = 'Drug'
        entity_type_var = 'drug'
        entity_options = {d.id: d for d in Drug.objects.all().order_by('name')}
        tag_list = DrugTag.objects.filter(tag_owner_filter).order_by(
                F('owner_id').asc(nulls_last=True), 'tag_category',
                'tag_name', 'drug__name')
        for tag in tag_list:
            tag_dict_selected.setdefault(tag.tag_category, {}).setdefault(
                tag.tag_name, []).append(entity_options[tag.drug_id])
    else:
        return render(request, "tags.html")

    tags_ids = {}
    for cat, tags in tag_dict_selected.items():
        tags_ids[cat] = {tag: [v.id for v in vals] for tag, vals in
                              tags.items()}

    return render(request, "tag_editor.html",
                  {'entity_type': entity_type,
                   'entity_type_var': entity_type_var,
                   'tag_type': tag_type,
                   'entities': entity_options,
                   'tags': dict(tag_dict_selected),
                   'public': tag_public,
                   'tags_ids': tags_ids
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


def ajax_upload_tagfile(request, tag_type):
    assert tag_type in ('cell_lines', 'drugs')

    if not request.user.is_authenticated():
        return JsonResponse({'error': 'Not logged in'}, status=401)

    files = request.FILES.getlist('tagfiles[]')
    if len(files) == 0:
        return JsonResponse({'error': 'No files uploaded'}, status=400)

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

        EntityClass = CellLine if tag_type == 'cell_lines' else Drug
        ent_col = 'cell_line' if tag_type == 'cell_lines' else 'drug'
        ent_name = 'Cell lines' if tag_type == 'cell_lines' else 'Drugs'

        ent_mapping = {ent.name.lower(): ent.id for ent in
                       EntityClass.objects.all()}

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

        if tag_type == 'cell_lines':
            CellLineTag.objects.bulk_create(
                CellLineTag(tag_name=row.tag_name,
                            tag_category=row.tag_category,
                            cell_line_id=ent_mapping[row.ent_lower],
                            owner=request.user)
                for row in csv.itertuples())
        else:
            DrugTag.objects.bulk_create(
                DrugTag(tag_name=row.tag_name,
                        tag_category=row.tag_category,
                        drug_id=ent_mapping[row.ent_lower],
                        owner=request.user)
                for row in csv.itertuples())

    return JsonResponse({'success': True})


def ajax_assign_tag(request):
    if not request.user.is_authenticated():
        return JsonResponse({}, status=401)

    try:
        tag_name = request.POST.get('tagName')
        if tag_name == '':
            raise ValueError('Empty tag name')
        tag_type = request.POST.get('tagType')
        if tag_type not in ('cl', 'drug'):
            raise ValueError('Unknown tag type')
        entity_ids = [int(e_id) for e_id in request.POST.getlist('entityId')]

        tag_category = request.POST.get('tagCategory')
        if tag_category == '':
            tag_category = None

        tag_public = request.POST.get('tagPublic') == '1'
    except (KeyError, ValueError):
        return JsonResponse({'error': 'Form not properly formatted'},
                            status=400)

    if tag_public and not request.user.is_staff:
        return JsonResponse({'error': 'Staff only'}, status=403)

    owner = None if tag_public else request.user

    tag_cls = DrugTag if tag_type == 'drug' else CellLineTag

    # Clear any existing instances of the tag
    tag_cls.objects.filter(tag_name=tag_name,
                           tag_category=tag_category, owner=owner).delete()

    if tag_type == 'drug':
        tags_to_create = [
            DrugTag(tag_name=tag_name, tag_category=tag_category,
                    owner=owner, drug_id=drug_id)
            for drug_id in entity_ids
        ]
    else:
        tags_to_create = [
            CellLineTag(tag_name=tag_name, tag_category=tag_category,
                        owner=owner, cell_line_id=cell_line_id)
            for cell_line_id in entity_ids
        ]

    entity_ids = []
    if tags_to_create:
        tag_cls.objects.bulk_create(tags_to_create)

        # Postgres automatically gets primary keys, but to be sure...
        if tags_to_create[0].pk is None:
            tags_to_create = tag_cls.objects.filter(
                tag_name=tag_name, tag_category=tag_category,
                owner=owner)

        if tag_type == 'drug':
            entity_ids = [t.drug_id for t in tags_to_create]
        else:
            entity_ids = [t.cell_line_id for t in tags_to_create]

    logger.info('Tag modified', extra={'request': request})

    return JsonResponse({
        'status': 'success',
        'tagName': tag_name,
        'tagCategory': tag_category,
        'public': tag_public,
        'entityIds': entity_ids
    })
