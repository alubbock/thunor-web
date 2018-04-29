from django.shortcuts import render
from django.http import JsonResponse
from django.db.models import Q
from thunorweb.models import CellLine, Drug, CellLineTag, DrugTag
from thunorweb.views import login_required_unless_public, login_required
import logging
import pandas as pd
from django.db.utils import IntegrityError
from guardian.shortcuts import assign_perm, remove_perm, get_groups_with_perms
from django.contrib.auth.models import Group
import collections

logger = logging.getLogger(__name__)
TAG_EVERYTHING_ELSE = -1


@login_required_unless_public
def tag_editor(request, tag_type=None):
    entity_options = None

    if tag_type == 'cell_lines':
        entity_type = 'Cell Line'
        entity_type_var = 'cl'
        if request.user.is_authenticated():
            entity_options = {c.id: c for c in CellLine.objects.all().order_by(
                'name')}
    elif tag_type == 'drugs':
        entity_type = 'Drug'
        entity_type_var = 'drug'
        if request.user.is_authenticated():
            entity_options = {d.id: d for d in Drug.objects.all().order_by(
                'name')}
    else:
        return render(request, "tags.html")

    return render(request, "tag_editor.html",
                  {'entity_type': entity_type,
                   'entity_type_var': entity_type_var,
                   'tag_type': tag_type,
                   'entities': entity_options,
                   }
                  )


def ajax_get_tags(request, tag_type, group=None):
    if tag_type not in ('cell_lines', 'drugs'):
        return JsonResponse({'error': 'Tag type not recognised'}, status=400)

    tag_cls = DrugTag if tag_type == 'drugs' else CellLineTag

    if group is None:
        if not request.user.is_authenticated():
            return JsonResponse({'error', 'Authentication required'},
                                status=401)
        perm_filter = Q(owner=request.user)
    elif group == 'public':
        if tag_type == 'drugs':
            perm_filter = Q(drugtaggroupobjectpermission__group__name='Public')
        else:
            perm_filter = Q(celllinetaggroupobjectpermission__group__name
                            ='Public')
    else:
        if tag_type == 'drugs':
            perm_filter = Q(drugtaggroupobjectpermission__group_id=group)
        else:
            perm_filter = Q(celllinetaggroupobjectpermission__group_id=group)

    tags = tag_cls.objects.filter(perm_filter).prefetch_related(tag_type)

    return JsonResponse({
        'data': [{'tag': {'id': tag.id, 'name': tag.tag_name, 'editable':
                          tag.owner_id == request.user.id},
                  'cat': tag.tag_category,
                  'targets': [t.name for t in (tag.drugs if tag_type ==
                                               'drugs' else
                                               tag.cell_lines).all()]
                  }
                 for tag in tags]
    })


@login_required
def ajax_get_tag_targets(request, tag_type, tag_id):
    tag_cls = DrugTag if tag_type == 'drugs' else CellLineTag
    try:
        tag = tag_cls.objects.filter(owner=request.user).get(id=tag_id)
    except tag_cls.DoesNotExist:
        raise JsonResponse({'error': 'Tag not found'}, status=404)

    groups = request.user.groups.all()

    groups_with_perms = get_groups_with_perms(tag)

    return JsonResponse({
        'tagId': tag.id,
        'tagName': tag.tag_name,
        'tagCategory': tag.tag_category,
        'targets': [t.id for t in (
                    tag.drugs if tag_type == 'drugs' else
                    tag.cell_lines).all()],
        'groups': [{'groupId': g.id, 'groupName': g.name,
                    'canView': g in groups_with_perms} for g in groups]
    })


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

    try:
        tag = tag_cls.objects.create(
            owner=request.user,
            tag_name=tag_name,
            tag_category=tag_category
        )
    except IntegrityError:
        return JsonResponse({
            'error': 'A tag with this name and category already exists'
        }, status=409)

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
        orig_name_mapping = csv[['ent_lower', ent_col]]

        csv = csv[['tag_name', 'tag_category', 'ent_lower']]
        duplicates = csv.duplicated()
        if duplicates.any():
            duplicates = csv[duplicates].iloc[0, :]
            dup_str = ','.join([duplicates['tag_category'], duplicates[
                'tag_name'], duplicates['ent_lower']])
            return JsonResponse({'error': 'File contains duplicates, '
                                          'e.g. {}'.format(dup_str)})

        missing_ents = set(csv['ent_lower']).difference(ent_mapping.keys())
        ents_created = []
        if missing_ents:
            create_ents = request.POST.get('createEntities', 'false') == 'true'
            if create_ents:
                orig_name_mapping = orig_name_mapping.set_index(
                    'ent_lower').iloc[:, 0]
                ents_to_add = [orig_name_mapping.loc[name] for name in
                               missing_ents]
                ents = [EntityClass(name=name) for name in ents_to_add]
                EntityClass.objects.bulk_create(ents)
                if ents[0].pk is None:
                    ents = EntityClass.objects.filter(name__in=ents_to_add)

                ent_mapping.update({ent.name.lower(): ent.id for ent in
                                    ents})
                ents_created = [{'id': ent.id, 'name': ent.name} for ent in
                                ents]
            else:
                return JsonResponse({
                    'error': '{} not found (shown in lower case): {}'.format(
                        ent_name, missing_ents)})

        # Get user's existing tags to check for conflicts
        existing_tags = collections.defaultdict(set)
        for tag in TagClass.objects.filter(owner=request.user):
            existing_tags[tag.tag_category].add(tag.tag_name)

        grpby = csv.groupby(['tag_category', 'tag_name'])
        tags = []
        for grp, _ in grpby:
            try:
                if grp[1] in existing_tags[grp[0]]:
                    return JsonResponse({'error': '"{}" in category "{}" '
                                         'already exists'.format(
                        grp[1], grp[0])}, status=400)
            except KeyError:
                pass
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

    return JsonResponse({'success': True, 'entitiesCreated': ents_created})


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


@login_required
def ajax_set_tag_group_permission(request):
    try:
        tag_id = int(request.POST['tag_id'])
        tag_type = request.POST['tag_type']
        group_id = int(request.POST['group_id'])
        state = request.POST['state'].lower() == 'true'
    except (KeyError, ValueError):
        return JsonResponse({'error': 'Malformed request'}, status=400)

    tag_cls = DrugTag if tag_type == 'drugs' else CellLineTag

    try:
        tag = tag_cls.objects.get(pk=tag_id, owner=request.user)
    except tag_cls.DoesNotExist:
        return JsonResponse({}, status=404)

    # Is user a member of the requested group?
    try:
        group = request.user.groups.get(pk=group_id)
    except Group.DoesNotExist:
        return JsonResponse({}, status=404)

    # Assign or remove the permission as requested
    permission_fn = assign_perm if state else remove_perm
    permission_fn('view', group, tag)

    return JsonResponse({'success': True})
