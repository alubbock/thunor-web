from django.shortcuts import render
from django.http import JsonResponse
from django.db.models import Q, F
from thunorweb.models import CellLine, Drug, CellLineTag, DrugTag
from thunorweb.views import login_required_unless_public
import logging

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
