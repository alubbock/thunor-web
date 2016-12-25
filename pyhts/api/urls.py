from django.conf.urls import url
from .views import PlateLayout, DatasetDetail, DatasetAssays, APIRoot, \
    GroupList, GroupDatasets

app_name = 'api'
urlpatterns = [
    url(r'^$', APIRoot.as_view()),

    url(r'^datasets/$', DatasetDetail.as_view(), name='dataset-list'),
    url(r'^datasets/(?P<pk>\d+)/$', DatasetDetail.as_view(),
        name='dataset-detail'),
    url(r'^datasets/(?P<dataset_id>\d+)/assays/(?P<assay>[^/]+)/$',
        DatasetAssays.as_view(), name='dataset-assay'),
    url(r'^plates/(?P<pk>\d+)/layout/$', PlateLayout.as_view(),
        name='plate-layout'),

    url(r'^groups/$', GroupList.as_view(), name='group-list'),
    url(r'^datasets/by-group-id/(?P<pk>\d+)/$', GroupDatasets.as_view(),
        name='group-datasets')
]
