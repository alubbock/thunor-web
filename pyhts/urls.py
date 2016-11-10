from django.conf.urls import url, include

from . import views

app_name = 'pyhts'
urlpatterns = [
    url(r'^$', views.home, name='home'),
    url('^logout$', views.logout, name='logout'),
    url(r'^upload$', views.PlateUpload.as_view(), name='plate_upload'),
    url(r'^annotate/(?P<dataset_id>\d+)$', views.plate_designer,
        name='plate_designer'),

    # url(r'^ajax/plate_file/(?P<file_id>\d+)$', views.ajax_get_plates,
    #     name='ajax_plate_names'),

    url(r'^ajax/plate/table_view', views.ajax_table_view,
        name='ajax_table_view'),
    url(r'^ajax/plate/save', views.ajax_save_plate,
        name='ajax_save_plate'),

    url(r'^ajax/dataset/create', views.ajax_create_dataset,
        name='ajax_create_dataset'),
    url(r'^ajax/dataset/set_timepoints', views.ajax_set_timepoints,
        name='ajax_set_timepoints'),
    url(r'^ajax/cellline/create', views.ajax_create_cellline,
        name='ajax_create_cellline'),
    url(r'^ajax/drug/create', views.ajax_create_drug,
        name='ajax_create_drug')
]
