from django.conf.urls import url
from django.contrib.auth import views as django_auth
from . import views

app_name = 'pyhts'
urlpatterns = [
    url(r'^$', views.home, name='home'),

    url('^accounts/$', views.my_account, name='my_account'),
    url('^logout$', views.logout, name='logout'),

    url(r'^dataset/add$', views.dataset_upload, name='plate_upload'),
    url(r'^dataset/(?P<dataset_id>\d+)/$', views.view_dataset,
        name='view_dataset'),
    url(r'^dataset/(?P<dataset_id>\d+)/upload$', views.dataset_upload,
        name='plate_upload'),
    url(r'^dataset/(?P<dataset_id>\d+)/annotate$', views.plate_designer,
        name='plate_designer'),

    url(r'^dataset/(?P<dataset_id>\d+)/download/annotations$',
        views.xlsx_get_annotation_data, name='download_dataset_annotation'),
    url(r'^dataset/(?P<dataset_id>\d+)/download/assays$',
        views.xlsx_get_assay_data, name='download_dataset_assays'),

    url(r'^dataset/(?P<dataset_id>\d+)/plots$', views.plots, name='plots'),


    url(r'^ajax/plot$', views.ajax_get_plot,
        name='ajax_plot'),

    url(r'^ajax/dataset/(?P<dataset_id>\d+)/groupings$',
        views.ajax_get_dataset_groupings, name='ajax_dataset_groupings'),

    url(r'^ajax/platefile/upload', views.ajax_upload_platefiles,
        name='ajax_upload_platefiles'),
    url('^ajax/platefile/delete', views.ajax_delete_platefile,
        name='ajax_delete_platefile'),

    url(r'^ajax/plate/load/(?P<plate_id>\d+)', views.ajax_load_plate,
        name='ajax_load_plate'),
    url(r'^ajax/plate/save', views.ajax_save_plate,
        name='ajax_save_plate'),

    url(r'^ajax/dataset/all', views.ajax_get_datasets,
        name='ajax_get_datasets'),
    url(r'^ajax/dataset/by-group/(?P<group_id>\d+)',
        views.ajax_get_datasets_group, name='ajax_get_datasets_by_group'),

    url(r'^ajax/dataset/create', views.ajax_create_dataset,
        name='ajax_create_dataset'),
    url(r'^ajax/cellline/create', views.ajax_create_cellline,
        name='ajax_create_cellline'),
    url(r'^ajax/drug/create', views.ajax_create_drug,
        name='ajax_create_drug')
]
