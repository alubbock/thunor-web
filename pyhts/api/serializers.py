from rest_framework import serializers
from pyhts.models import Well, WellMeasurement, WellDrug, Plate, HTSDataset,\
    CellLine, Drug
from django.contrib.auth.models import Group


class GroupSerializer(serializers.ModelSerializer):
    datasets = serializers.HyperlinkedIdentityField(
        view_name='pyhts:api:group-datasets', read_only=True)

    class Meta:
        model = Group
        fields = ('id', 'name', 'datasets')


# class RawWellMeasurementSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = WellMeasurement
#         fields = ('assay', 'timepoint', 'value')


# class WellDataSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Well
#         fields = ('well_num', '')


# class PlateMeasurementSerializer(serializers.ModelSerializer):
#     wells = WellDataSerializer(many=True, read_only=True)
#
#     class Meta:
#         model = Plate
#         fields = ('name', 'dataset_name', 'dataset', 'last_annotated',
#                   'width', 'height', 'wells')


# Annotation classes
#
# class CellLineSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = CellLine
#         fields = ('id', 'name')
#
#
# class DrugSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Drug
#         fields = ('id', 'name')


class WellDrugSerializer(serializers.ModelSerializer):
    drug = serializers.ReadOnlyField(source='drug.name')

    class Meta:
        model = WellDrug
        fields = ('order', 'drug', 'dose')


class WellLayoutSerializer(serializers.ModelSerializer):
    drugs = WellDrugSerializer(many=True, read_only=True)
    cell_line = serializers.ReadOnlyField(source='cell_line.name')

    class Meta:
        model = Well
        fields = ('well_num', 'cell_line', 'drugs')


class PlateLayoutSerializer(serializers.ModelSerializer):
    wells = WellLayoutSerializer(many=True, read_only=True)
    dataset_name = serializers.ReadOnlyField(source='dataset.name')
    dataset = serializers.HyperlinkedRelatedField(
        view_name='pyhts:api:dataset-detail', read_only=True)

    class Meta:
        model = Plate
        fields = ('name', 'dataset_name', 'dataset', 'last_annotated',
                  'width', 'height', 'wells')


# Basic dataset summary

class BasicPlateSerializer(serializers.ModelSerializer):
    layout = serializers.HyperlinkedIdentityField(
        view_name='pyhts:api:plate-layout')

    class Meta:
        model = Plate
        fields = ('name', 'num_wells', 'layout')


class HTSDatasetSummarySerializer(serializers.ModelSerializer):
    read_only = True
    plates = BasicPlateSerializer(many=True, read_only=True)
    owner = serializers.StringRelatedField(read_only=True)
    assays = serializers.SerializerMethodField()
    last_annotated = serializers.SerializerMethodField()

    class Meta:
        model = HTSDataset
        fields = ('name', 'owner', 'creation_date', 'last_annotated',
                  'assays', 'plates')

    def __init__(self, *args, **kwargs):
        self._assays = kwargs.pop('assays', None)

        super(HTSDatasetSummarySerializer, self).__init__(*args, **kwargs)

    def get_last_annotated(self, obj):
        try:
            return max([p.last_annotated for p in obj.plates.all() if
                        p.last_annotated is not None])
        except ValueError:
            return None

    def get_assays(self, obj):
        # return WellMeasurement.objects.filter(
        #     well__plate__dataset=obj.pk).values('assay').distinct(
        #
        # ).values_list('assay', flat=True)
        return self._assays[obj.pk]


class DatasetAssaySerializer(serializers.Serializer):
    read_only = True
    combinations = serializers.SerializerMethodField()

    class Meta:
        fields = ('combinations', )

    def get_combinations(self):
        pass
