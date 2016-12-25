from rest_framework.views import Response
from rest_framework.generics import GenericAPIView
from rest_framework.authentication import SessionAuthentication
from rest_framework import permissions
from .serializers import PlateLayoutSerializer, HTSDatasetSummarySerializer,\
    DatasetAssaySerializer, GroupSerializer
from pyhts.models import HTSDataset, CellLine, Plate, WellDrug, WellMeasurement
from django.shortcuts import get_object_or_404
from rest_framework.reverse import reverse
import collections
from django.contrib.auth.models import Group
from guardian.shortcuts import get_objects_for_group
from django.contrib.contenttypes.models import ContentType


class HTSDatasetReadPermission(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated():
            return False

        if request.method not in permissions.SAFE_METHODS:
            return False

        if isinstance(obj, HTSDataset):
            dataset_obj = obj
        elif isinstance(obj, Plate):
            dataset_obj = obj.dataset
        else:
            raise ValueError('Unsupported object type: %s' % type(obj))

        if dataset_obj.owner_id == request.user.id:
            return True

        return request.user.has_perm('download_data', dataset_obj)


class GroupPermission(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated():
            return False

        if request.method not in permissions.SAFE_METHODS:
            return False

        try:
            request.user.groups.get(pk=obj.pk)
            return True
        except Group.DoesNotExist:
            return False


class ThunorAPIView(GenericAPIView):
    """
    API View with default authentication and permission
    """
    authentication_classes = (SessionAuthentication, )
    permission_classes = (permissions.IsAuthenticated, )


class ThunorDatasetAPIView(ThunorAPIView):
    permission_classes = (permissions.IsAuthenticated,
                          HTSDatasetReadPermission)


class APIRoot(ThunorAPIView):
    """
    Welcome to the Thunor API!
    """
    def get(self, request, format=None):
        return Response({
            'datasets': reverse('pyhts:api:dataset-list', request=request,
                                format=format),
            'groups': reverse('pyhts:api:group-list', request=request,
                              format=format)
        })


class GroupList(ThunorAPIView):
    serializer_class = GroupSerializer

    def get(self, request, *args, **kwargs):
        groups = request.user.groups.all()
        serializer = self.serializer_class(groups, many=True,
                                           context={'request': request})
        return Response({'groups': serializer.data})

    def get_queryset(self):
        return None


class GroupDatasets(ThunorAPIView):
    queryset = HTSDataset.objects.all()
    serializer_class = HTSDatasetSummarySerializer

    def get(self, request, *args, **kwargs):
        group = get_object_or_404(request.user.groups.filter(pk=kwargs[
                                  'pk']))

        self.check_object_permissions(request, group)

        try:
            datasets = list(get_objects_for_group(
                group,
                HTSDataset.view_dataset_permission_names(),
                klass=HTSDataset,
                any_perm=True
            ))

            assay_query = WellMeasurement.objects.filter(
                well__plate__dataset_id__in=[d.id for d in datasets])
            assays = _assays_from_wellmeasurements(assay_query, request,
                                                   format=kwargs.get(
                                                       'format', None))
        except ContentType.DoesNotExist:
            datasets = []
            assays = []

        serializer = self.serializer_class(
            datasets, many=True, assays=assays, context={'request': request})
        return Response({
            'group_id': group.id,
            'group_name': group.name,
            'datasets': serializer.data})


def _assays_from_wellmeasurements(assay_query, request, format=None):
    assays = collections.defaultdict(list)
    for a in assay_query.values('well__plate__dataset', 'assay').distinct(
    ).values('well__plate__dataset', 'assay'):
        assays[a['well__plate__dataset']].append({
            'name': a['assay'],
            'url': reverse('pyhts:api:dataset-assay',
                           args=[a['well__plate__dataset'],
                                 a['assay']],
                           request=request,
                           format=format)
        })
    return assays


class DatasetDetail(ThunorDatasetAPIView):
    queryset = HTSDataset.objects.all().order_by(
        '-creation_date').prefetch_related('plates').select_related('owner')
    serializer_class = HTSDatasetSummarySerializer

    def get(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        multiple = False
        if 'pk' in kwargs:
            queryset = queryset.get(pk=kwargs['pk'])
            self.check_object_permissions(request, queryset)
            assay_query = WellMeasurement.objects.filter(
                well__plate__dataset=kwargs['pk'])
        else:
            multiple = True
            queryset = queryset.filter(owner_id=request.user.id)
            assay_query = WellMeasurement.objects.filter(
                well__plate__dataset__owner_id=request.user.id)

        assays = _assays_from_wellmeasurements(assay_query, request,
                                               kwargs.get('format', None))

        serializer = self.serializer_class(queryset,
                                           many=multiple,
                                           assays=assays,
                                           context={'request': request}
                                           )
        return Response({'dataset' + ('s' if multiple else ''):
                         serializer.data})


class PlateLayout(ThunorDatasetAPIView):
    """
    View the layout of a plate
    """
    serializer_class = PlateLayoutSerializer

    def get(self, request, *args, **kwargs):
        pk = kwargs['pk']
        plate = self.get_queryset().get(pk=pk)
        self.check_object_permissions(request, plate)
        serializer = self.serializer_class(plate, context={'request': request})
        return Response(serializer.data)

    def get_queryset(self):
        return Plate.objects.select_related('dataset').prefetch_related(
            'wells', 'wells__drugs',
            'wells__drugs__drug', 'wells__cell_line')


class DatasetAssays(ThunorDatasetAPIView):
    """
    View cell line/drug combos for a particular dataset and assay
    """
    serializer_class = DatasetAssaySerializer

    def get(self, request, *args, **kwargs):
        dataset = get_object_or_404(HTSDataset.objects.filter(
            pk=kwargs['dataset_id']))

        self.check_object_permissions(request, dataset)

        wells = collections.OrderedDict()
        for wd in WellDrug.objects.filter(
                well__plate__dataset_id=kwargs['dataset_id'],
                well__data__assay=kwargs['assay'],
                drug__isnull=False,
                well__cell_line__isnull=False
                    ).select_related('well', 'drug',
                                     'well__cell_line').order_by(
                'well__cell_line', 'well_id'):
            wells.setdefault((wd.well.cell_line, wd.well_id),
                             {})[wd.order] = wd.drug

        combinations = collections.OrderedDict()
        for w, drugs in wells.items():
            combinations[(w[0], tuple(drugs.values()))] = None

        response = [{
            'cell_line': c[0].name,
            'drugs': [d.name for d in c[1]]
        } for c in combinations.keys()]

        return Response({
            'dataset_name': dataset.name,
            'dataset': reverse('pyhts:api:dataset-detail', args=[
                dataset.id], request=request, format=kwargs.get('format',
                                                                None)),
            'combinations': response})
