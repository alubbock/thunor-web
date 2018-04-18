from django.shortcuts import render
from django.http import JsonResponse
from django.db.models import Q, F
from thunorweb.models import CellLine, Drug, CellLineTag, DrugTag
from collections import defaultdict, namedtuple
from thunorweb.views import login_required_unless_public
import logging

logger = logging.getLogger(__name__)


@login_required_unless_public
def tag_editor(request, tag_type=None):
    if request.user.is_authenticated():
        tag_owner_filter = Q(owner=request.user) | Q(owner=None)
    else:
        tag_owner_filter = Q(owner=None)

    Tag = namedtuple('Tag', ['is_public', 'tag_category', 'tag_name'])
    tag_dict_selected = defaultdict(list)
    tag_dict_all = {}
    if tag_type == 'cell_lines':
        entity_type = 'Cell Line'
        entity_type_var = 'cl'
        entity_options = CellLine.objects.all().order_by('name')
        tag_list = CellLineTag.objects.filter(tag_owner_filter).order_by(
                F('owner_id').asc(nulls_last=True), 'tag_category', 'tag_name',
                'cell_line__name')
        for tag in tag_list:
            tag_dict_selected[Tag(tag.owner_id is None,
                                  tag.tag_category, tag.tag_name)].append(
                tag.cell_line_id)
        for tag_key, cell_lines in tag_dict_selected.items():
            tag_dict_all[tag_key] = [(ent, ent.id in cell_lines) for ent in
                                     entity_options]
    elif tag_type == 'drugs':
        entity_type = 'Drug'
        entity_type_var = 'drug'
        entity_options = Drug.objects.all().order_by('name')
        tag_list = DrugTag.objects.filter(tag_owner_filter).order_by(
                F('owner_id').asc(nulls_last=True), 'tag_category',
                'tag_name', 'drug__name')
        for tag in tag_list:
            tag_dict_selected[Tag(tag.owner_id is None,
                                  tag.tag_category, tag.tag_name)].append(
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
