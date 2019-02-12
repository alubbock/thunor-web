from django.shortcuts import render
from django.http import JsonResponse
from django.db import transaction
from django.db.models import Q
from thunorweb.models import CellLine, Drug, CellLineTag, DrugTag
from thunorweb.views import login_required_unless_public, login_required
import logging
import pandas as pd
from django.db.utils import IntegrityError
from guardian.shortcuts import assign_perm, remove_perm, \
    get_groups_with_perms, get_objects_for_user
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
        if request.user.is_authenticated:
            entity_options = {c.id: c for c in CellLine.objects.all().order_by(
                'name')}
    elif tag_type == 'drugs':
        entity_type = 'Drug'
        entity_type_var = 'drug'
        if request.user.is_authenticated:
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
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required. Please log '
                                          'in.'}, status=401)
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

    tags = tag_cls.objects.filter(perm_filter).prefetch_related(
        tag_type).prefetch_related('owner')

    return JsonResponse({
        'data': [{'tag': {'id': tag.id, 'name': tag.tag_name, 'editable':
                          tag.owner_id == request.user.id,
                          'ownerEmail': tag.owner.email
                          },
                  'cat': tag.tag_category,
                  'targets': [t.name for t in (tag.drugs if tag_type ==
                                               'drugs' else
                                               tag.cell_lines).all()]
                  }
                 for tag in tags]
    })


def ajax_get_tag_targets(request, tag_type, tag_id):
    if not request.user.is_authenticated:
        return JsonResponse({}, status=401)

    tag_cls = DrugTag if tag_type == 'drugs' else CellLineTag
    try:
        tag = tag_cls.objects.filter(owner=request.user).get(id=tag_id)
    except tag_cls.DoesNotExist:
        return JsonResponse({'error': 'Tag not found'}, status=404)

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


def ajax_get_tag_groups(request, tag_type):
    if not request.user.is_authenticated:
        return JsonResponse({}, status=401)

    tag_cls = DrugTag if tag_type == 'drugs' else CellLineTag
    try:
        tag_ids = request.GET.getlist('tagId')
    except KeyError:
        return JsonResponse({'error': 'Malformed request'}, status=400)

    tags = tag_cls.objects.filter(owner=request.user, pk__in=tag_ids)
    if len(tags) < len(tag_ids):
        return JsonResponse({'error': 'Some tags are not owned by you or '
                                      'have not been found'}, status=400)

    user_groups = request.user.groups.all()
    tag_groups = {tag.id: get_groups_with_perms(tag) for tag in tags}
    # Invert tag_groups to get group_tags
    group_tags = {g.id: set() for g in user_groups}
    for tag_id, groups in tag_groups.items():
        for group in groups:
            group_tags[group.id].add(tag_id)

    return JsonResponse({'groups': [{
        'groupId': g.id,
        'groupName': g.name,
        'tagIds': list(group_tags[g.id])
    } for g in user_groups]})


@transaction.atomic
def ajax_create_tag(request):
    if not request.user.is_authenticated:
        return JsonResponse({}, status=401)

    try:
        tag_name = request.POST['tagsName']
        tag_category = request.POST['tagCategory']
        tag_type = request.POST['tagType']
    except KeyError:
        return JsonResponse({'error': 'Form not properly formatted'},
                            status=400)

    if tag_type not in ('cl', 'drug'):
        return JsonResponse({'error': 'Tag type not recognised'}, stauts=400)

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

    # Assign tag targets, if any supplied
    try:
        entity_ids = [int(e_id) for e_id in request.POST.getlist('entityId')]
    except KeyError:
        entity_ids = []

    if 'entityName' in request.POST:
        if entity_ids:
            transaction.set_rollback(True)
            return JsonResponse({'error': 'Supply either entityId or '
                                          'entityName, not both'},
                                status=400)

        entity_names = request.POST.getlist('entityName')
        entity_cls = Drug if tag_type == 'drug' else CellLine
        entities = entity_cls.objects.filter(name__in=entity_names)
        if len(entities) < len(entity_names):
            transaction.set_rollback(True)
            entity_names_db = set(e.name for e in entities)
            missing_names = set(entity_names).difference(entity_names_db)
            return JsonResponse({'error': 'Entity names not found in database: '
                                 + ','.join(missing_names)}, status=400)
        entity_ids = [e.id for e in entities]

    if entity_ids:
        if tag_type == 'drug':
            tag.drugs.set(entity_ids)
        else:
            tag.cell_lines.set(entity_ids)

    return JsonResponse({
        'success': True,
        'tagId': tag.id,
        'tagName': tag.tag_name,
        'tagCategory': tag.tag_category,
        'tagType': tag_type,
        'entityIds': entity_ids
    })


def ajax_rename_tag(request):
    if not request.user.is_authenticated:
        return JsonResponse({}, status=401)

    try:
        tag_id = request.POST['tagId']
        tag_name = request.POST['tagsName']
        tag_category = request.POST.get('tagCategory', '')
        tag_type = request.POST.get('tagType')
        if tag_type not in ('cl', 'drug'):
            raise ValueError
    except (KeyError, ValueError):
        return JsonResponse({'error': 'Form not properly formatted'},
                            status=400)

    tag_cls = DrugTag if tag_type == 'drug' else CellLineTag

    perm_query = Q(owner=request.user)

    n_updated = tag_cls.objects.filter(perm_query).filter(
        id=tag_id).update(tag_name=tag_name, tag_category=tag_category)

    if n_updated == 0:
        return JsonResponse({'error': 'Tag not found'}, status=404)

    return JsonResponse({
        'success': True,
        'tagId': tag_id,
        'tagName': tag_name,
        'tagCategory': tag_category,
        'tagType': tag_type
    })


@transaction.atomic
def ajax_delete_tag(request):
    if not request.user.is_authenticated:
        return JsonResponse({}, status=401)

    try:
        tag_id = request.POST.getlist('tagId')
        if not tag_id:
            tag_id = request.POST.getlist('tagId[]')
        tag_id = [int(t) for t in tag_id]
        tag_type = request.POST.get('tagType')
        if tag_type not in ('cl', 'drug'):
            raise ValueError
    except (KeyError, ValueError):
        return JsonResponse({'error': 'Form not properly formatted'},
                            status=400)

    if not tag_id:
        return JsonResponse({'error': 'No tagId specified'}, status=400)

    tag_cls = DrugTag if tag_type == 'drug' else CellLineTag

    _, deletions = tag_cls.objects.filter(
        owner=request.user, id__in=tag_id).delete()

    deleted_cls = '{}.{}'.format(tag_cls._meta.app_label,
                                 tag_cls._meta.object_name)

    if deletions.get(deleted_cls) != len(tag_id):
        transaction.set_rollback(True)
        return JsonResponse({'error': 'Tag(s) requested not found, or you '
                                      'don\'t have permission to delete (some '
                                      'of) them'}, status=400)

    return JsonResponse({'success': True, 'tagId': tag_id})


@transaction.atomic
def ajax_upload_tagfile(request, tag_type):
    assert tag_type in ('cell_lines', 'drugs')

    if not request.user.is_authenticated:
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
        if file.name.endswith('.txt') or file.name.endswith('.tsv'):
            sep = '\t'
        elif file.name.endswith('.csv'):
            sep = ','
        else:
            return JsonResponse({'error': 'File name must end with .txt'
                                          '(Tab separated) or .csv '
                                          '(Comma separated)'}, status=400)

        try:
            csv = pd.read_csv(file, sep=sep)
        except:
            transaction.set_rollback(True)
            return JsonResponse({
                'error': 'Could not read file. Please ensure file is comma '
                         'separated (with extension .csv) or tab separated ('
                         'with extension .txt or .tsv)'
             }, status=400)

        if 'tag_name' not in csv.columns:
            transaction.set_rollback(True)
            return JsonResponse({'error': 'Column tag_name not found'},
                                status=400)
        if 'tag_category' not in csv.columns:
            transaction.set_rollback(True)
            return JsonResponse({'error': 'Column tag_category not found'},
                                status=400)
        if tag_type == 'drugs' and 'drug' not in csv.columns:
            transaction.set_rollback(True)
            return JsonResponse({'error': 'Column drug not found'},
                                status=400)
        if tag_type == 'cell_lines' and 'cell_line' not in csv.columns:
            transaction.set_rollback(True)
            return JsonResponse({'error': 'Column cell_line not found'},
                                status=400)

        csv['ent_lower'] = csv[ent_col].str.lower()
        orig_name_mapping = csv[['ent_lower', ent_col]]

        csv = csv[['tag_name', 'tag_category', 'ent_lower']]
        duplicates = csv.duplicated()
        if duplicates.any():
            transaction.set_rollback(True)
            duplicates = csv[duplicates].iloc[0, :]
            dup_str = ','.join([duplicates['tag_category'], duplicates[
                'tag_name'], duplicates['ent_lower']])
            return JsonResponse({'error': 'File contains duplicates, '
                                          'e.g. {}'.format(dup_str)},
                                status=400)

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
                transaction.set_rollback(True)
                return JsonResponse({
                    'error': '{} not found (shown in lower case): {}'.format(
                        ent_name, missing_ents)}, status=400)

        # Get user's existing tags to check for conflicts
        existing_tags = collections.defaultdict(set)
        for tag in TagClass.objects.filter(owner=request.user):
            existing_tags[tag.tag_category].add(tag.tag_name)

        grpby = csv.groupby(['tag_category', 'tag_name'])
        tags = []
        for grp, _ in grpby:
            try:
                if grp[1] in existing_tags[grp[0]]:
                    transaction.set_rollback(True)
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
    if not request.user.is_authenticated:
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


def ajax_set_tag_group_permission(request):
    if not request.user.is_authenticated:
        return JsonResponse({}, status=401)

    try:
        tag_ids = [int(t) for t in request.POST.getlist('tag_id')]
        if not tag_ids:
            tag_ids = [int(t) for t in request.POST.getlist('tag_id[]')]
        tag_type = request.POST['tag_type']
        group_id = int(request.POST['group_id'])
        state = request.POST['state'].lower() == 'true'
    except (KeyError, ValueError):
        return JsonResponse({'error': 'Malformed request'}, status=400)

    if not tag_ids:
        return JsonResponse({'error': 'No tag IDs supplied'}, status=400)

    tag_cls = DrugTag if tag_type == 'drugs' else CellLineTag

    tags = tag_cls.objects.filter(pk__in=tag_ids, owner=request.user)

    if len(tags) < len(tag_ids):
        return JsonResponse({'error': 'You do not own all of the selected tags,'
                                      ' or they are no longer available.'},
                            status=400)

    # Is user a member of the requested group?
    try:
        group = request.user.groups.get(pk=group_id)
    except Group.DoesNotExist:
        return JsonResponse({}, status=404)

    # Assign or remove the permission as requested
    permission_fn = assign_perm if state else remove_perm
    permission_fn('view', group, tags)

    return JsonResponse({'success': True})


@transaction.atomic
def ajax_copy_tags(request):
    if not request.user.is_authenticated:
        return JsonResponse({}, status=401)

    try:
        tag_ids = [int(t) for t in request.POST.getlist('tagId')]
        tag_type = request.POST['tagType']
        copy_mode = request.POST['copyMode']
        tag_category = request.POST['tagCategory']
        tag_name = request.POST.get('tagName')
    except (KeyError, ValueError):
        return JsonResponse({'error': 'Malformed request'}, status=400)

    if copy_mode not in ('separate', 'union', 'intersection'):
        return JsonResponse({'error': 'Invalid copyMode'}, status=400)

    if tag_type not in ('cl', 'drug'):
        return JsonResponse({'error': 'Tag type not recognised'}, status=400)

    tag_cls = CellLineTag if tag_type == 'cl' else DrugTag

    # Get the tags which the user has permission to access
    tags = tag_cls.objects.filter(pk__in=tag_ids).intersection(
        get_objects_for_user(request.user, perms='view', klass=tag_cls)
    ).union(
        tag_cls.objects.filter(pk__in=tag_ids, owner=request.user)
    ).prefetch_related('cell_lines' if tag_type == 'cl' else 'drugs')

    if len(tags) < len(tag_ids):
        return JsonResponse({'error': 'You do not have permission to access at '
                                      'least some of the requested tags'},
                            status=400)

    # Create the tag(s) and assign the entries
    if copy_mode == 'separate':
        if tag_name is not None and len(tags) > 1:
            return JsonResponse({'error': 'Cannot set tag_name when copyMode="'
                                          'separate"'}, status=400)
        for tag in tags:
            new_tag_name = tag_name if tag_name is not None else tag.tag_name
            try:
                new_tag = tag_cls.objects.create(
                    owner=request.user,
                    tag_name=new_tag_name,
                    tag_category=tag_category
                )
            except IntegrityError:
                transaction.set_rollback(True)
                return JsonResponse({
                    'error': 'A tag called "{}" in category "{}" already '
                             'exists'.format(new_tag_name, tag_category)
                }, status=409)
            if tag_type == 'cl':
                new_tag.cell_lines.set(tag.cell_lines.all())
            else:
                new_tag.drugs.set(tag.drugs.all())
    else:
        # Merge or intersection mode
        entity_lbl = 'cell_lines' if tag_type == 'cl' else 'drugs'
        if copy_mode == 'intersection':
            entity_ids = set.intersection(
                *[set(getattr(tag, entity_lbl).all()) for tag in tags]
            )
        else:
            entity_ids = set.union(
                *[set(getattr(tag, entity_lbl).all()) for tag in tags]
            )
        try:
            new_tag = tag_cls.objects.create(
                owner=request.user,
                tag_name=tag_name,
                tag_category=tag_category
            )
        except IntegrityError:
            transaction.set_rollback(True)
            return JsonResponse({
                'error': 'A tag called "{}" in category "{}" already '
                         'exists'.format(tag_name, tag_category)
            }, status=409)
        getattr(new_tag, entity_lbl).set(entity_ids)

    return JsonResponse({'success': True})
