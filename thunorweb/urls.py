from django.urls import path, re_path
import thunorweb.views as views
import thunorweb.views.tags as tags
import thunorweb.views.plate_mapper as plate_mapper
import thunorweb.views.datasets as datasets
import thunorweb.views.dataset_downloads as downloads
import thunorweb.views.plots as plots

app_name = 'thunorweb'
urlpatterns = [
    path('', views.home, name='home'),

    path('accounts/password/reset/', views.reset_password,
         name='reset_password'),
    path('accounts', views.my_account, name='my_account'),
    path('logout', views.logout, name='logout'),

    path('tags', tags.tag_editor, name='tag_editor'),
    re_path('tags/(?P<tag_type>cell_lines|drugs)$', tags.tag_editor,
            name='tag_editor'),
    path('ajax/tags/rename', tags.ajax_rename_tag,
         name='ajax_rename_tag'),
    path('ajax/tags/assign', tags.ajax_assign_tag,
         name='ajax_assign_tag'),
    re_path(r'^tags/(?P<tag_type>cell_lines|drugs)/upload$',
            tags.ajax_upload_tagfile, name='ajax_upload_tagfile'),
    path('ajax/tags/create', tags.ajax_create_tag, name='ajax_create_tag'),
    path('ajax/tags/delete', tags.ajax_delete_tag, name='ajax_delete_tag'),
    re_path(r'^ajax/tags/(?P<tag_type>cell_lines|drugs)$',
            tags.ajax_get_tags, name='ajax_get_tags'),
    re_path(r'^ajax/tags/(?P<tag_type>cell_lines|drugs)/(?P<group>public|\d+)$',
            tags.ajax_get_tags, name='ajax_get_tags'),
    re_path(r'^ajax/tags/(?P<tag_type>cell_lines|drugs)/targets/(?P<tag_id>\d+)$',
            tags.ajax_get_tag_targets, name='ajax_get_tag_targets'),
    re_path(r'^ajax/tags/(?P<tag_type>cell_lines|drugs)/groups$',
            tags.ajax_get_tag_groups, name='ajax_get_tag_targets'),
    path('ajax/tags/set-permission',
         tags.ajax_set_tag_group_permission,
         name='ajax_set_tag_group_permission'),
    path('ajax/tags/copy', tags.ajax_copy_tags, name='ajax_copy_tags'),

    path('platemap', plate_mapper.plate_mapper,
         kwargs={'dataset_id': None}, name='plate_mapper'),
    re_path(r'^platemap/(?P<num_wells>\d+)$', plate_mapper.plate_mapper,
            kwargs={'dataset_id': None}, name='plate_mapper'),

    path('dataset/add', datasets.dataset_upload, name='plate_upload'),
    re_path(r'^dataset/(?P<dataset_id>\d+)$', datasets.view_dataset,
            name='view_dataset'),

    re_path(r'^dataset/(?P<dataset_id>\d+)/permissions$',
            datasets.view_dataset_permissions, name='view_dataset_permissions'),
    re_path(r'^dataset/(?P<dataset_id>\d+)/upload$', datasets.dataset_upload,
            name='plate_upload'),
    re_path(r'^dataset/(?P<dataset_id>\d+)/annotate$', plate_mapper.plate_mapper,
            name='plate_mapper_dataset'),

    re_path(r'^dataset/(?P<dataset_id>\d+)/download/hdf5$',
            downloads.download_dataset_hdf5, name='download_dataset_hdf5'),
    re_path(r'^dataset/(?P<dataset_id>\d+)/download/fit_params_'
            r'(?P<stat_type>viability|dip)$',
            downloads.download_fit_params, name='download_fit_params'),
    re_path(r'^dataset/(?P<dataset_id>\d+)/download/dip_rates$',
            downloads.download_dip_rates, name='download_dip_rates'),

    path('plots', plots.plots, name='plots'),

    re_path(r'^ajax/plot\.(?P<file_type>\w+)$', plots.ajax_get_plot,
            name='ajax_plot'),

    re_path(r'^ajax/dataset/(?P<dataset_id>\d+)(,(?P<dataset2_id>\d+))?/groupings$',
            datasets.ajax_get_dataset_groupings, name='ajax_dataset_groupings'),
    path('ajax/dataset/set-permission',
         datasets.ajax_set_dataset_group_permission,
         name='ajax_set_dataset_group_permission'),
    re_path('ajax/dataset/delete', datasets.ajax_delete_dataset,
            name='ajax_delete_dataset'),
    path('ajax/dataset/rename', datasets.ajax_rename_dataset,
         name='ajax_rename_dataset'),
    re_path(r'^ajax/dataset/(?P<dataset_id>\d+)/accept-license$',
            datasets.accept_license, name='accept_license'),

    path('ajax/platefile/upload', datasets.ajax_upload_platefiles,
         name='ajax_upload_platefiles'),
    path('ajax/platefile/delete', datasets.ajax_delete_platefile,
         name='ajax_delete_platefile'),

    re_path(r'^ajax/plate/load/(?P<plate_id>\d+)', plate_mapper.ajax_load_plate,
            name='ajax_load_plate'),
    path('ajax/plate/save', plate_mapper.ajax_save_plate,
         name='ajax_save_plate'),

    path('ajax/dataset/all', datasets.ajax_get_datasets,
         name='ajax_get_datasets'),
    re_path(r'^ajax/dataset/by-group/(?P<group_id>\d+|Public)',
            datasets.ajax_get_datasets_group, name='ajax_get_datasets_by_group'),

    path('ajax/dataset/create', datasets.ajax_create_dataset,
         name='ajax_create_dataset'),
    path('ajax/cellline/create', plate_mapper.ajax_create_cellline,
         name='ajax_create_cellline'),
    path('ajax/drug/create', plate_mapper.ajax_create_drug,
         name='ajax_create_drug')
]
