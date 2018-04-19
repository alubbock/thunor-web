from django.conf.urls import url
import thunorweb.views as views
import thunorweb.views.tags as tags
import thunorweb.views.plate_mapper as plate_mapper
import thunorweb.views.datasets as datasets
import thunorweb.views.dataset_downloads as downloads
import thunorweb.views.plots as plots

app_name = 'thunorweb'
urlpatterns = [
    url(r'^$', views.home, name='home'),

    url('^accounts$', views.my_account, name='my_account'),
    url('^logout$', views.logout, name='logout'),

    url(r'^tags$', tags.tag_editor, name='tag_editor'),
    url(r'^tags/(?P<tag_type>cell_lines|drugs)$', tags.tag_editor,
        name='tag_editor_private'),
    url(r'^tags/(?P<tag_type>cell_lines|drugs)/public$', tags.tag_editor,
        name='tag_editor', kwargs={'tag_public': True}),
    # url(r'^ajax/tags/set_name$', views.ajax_set_tag_name,
    #     name='ajax_set_tag_name'),
    url(r'^ajax/tags/assign$', tags.ajax_assign_tag,
        name='ajax_assign_tag'),

    url(r'platemap$', plate_mapper.plate_mapper,
        kwargs={'dataset_id': None}, name='plate_mapper'),
    url(r'^platemap/(?P<num_wells>\d+)$', plate_mapper.plate_mapper,
        kwargs={'dataset_id': None}, name='plate_mapper'),

    url(r'^dataset/add$', datasets.dataset_upload, name='plate_upload'),
    url(r'^dataset/(?P<dataset_id>\d+)$', datasets.view_dataset,
        name='view_dataset'),

    url(r'^dataset/(?P<dataset_id>\d+)/permissions$',
        datasets.view_dataset_permissions, name='view_dataset_permissions'),
    url(r'^dataset/(?P<dataset_id>\d+)/upload$', datasets.dataset_upload,
        name='plate_upload'),
    url(r'^dataset/(?P<dataset_id>\d+)/annotate$', plate_mapper.plate_mapper,
        name='plate_designer'),

    url(r'^dataset/(?P<dataset_id>\d+)/download/hdf5$',
        downloads.download_dataset_hdf5, name='download_dataset_hdf5'),
    url(r'^dataset/(?P<dataset_id>\d+)/download/fit_params$',
        downloads.download_dip_fit_params, name='download_dip_fit_params'),

    url(r'^plots$', plots.plots, name='plots'),

    url(r'^ajax/plot\.(?P<file_type>\w+)$', plots.ajax_get_plot,
        name='ajax_plot'),

    url(r'^ajax/dataset/(?P<dataset_id>\d+)(,(?P<dataset2_id>\d+))?/groupings$',
        datasets.ajax_get_dataset_groupings, name='ajax_dataset_groupings'),
    url(r'^ajax/dataset/set-permission$',
        datasets.ajax_set_dataset_group_permission,
        name='ajax_set_dataset_group_permission'),
    url(r'^ajax/dataset/delete', datasets.ajax_delete_dataset,
        name='ajax_delete_dataset'),

    url(r'^ajax/platefile/upload', datasets.ajax_upload_platefiles,
        name='ajax_upload_platefiles'),
    url('^ajax/platefile/delete', datasets.ajax_delete_platefile,
        name='ajax_delete_platefile'),

    url(r'^ajax/plate/load/(?P<plate_id>\d+)', plate_mapper.ajax_load_plate,
        name='ajax_load_plate'),
    url(r'^ajax/plate/save', plate_mapper.ajax_save_plate,
        name='ajax_save_plate'),

    url(r'^ajax/dataset/all', datasets.ajax_get_datasets,
        name='ajax_get_datasets'),
    url(r'^ajax/dataset/by-group/(?P<group_id>\d+|Public)',
        datasets.ajax_get_datasets_group, name='ajax_get_datasets_by_group'),

    url(r'^ajax/dataset/create', datasets.ajax_create_dataset,
        name='ajax_create_dataset'),
    url(r'^ajax/cellline/create', plate_mapper.ajax_create_cellline,
        name='ajax_create_cellline'),
    url(r'^ajax/drug/create', plate_mapper.ajax_create_drug,
        name='ajax_create_drug')
]
