from django.conf.urls import url
from django.views.generic import RedirectView
from . import views

app_name = 'thunorweb'
urlpatterns = [
    url(r'^$', views.home, name='home'),
    url(r'^incyte$', views.BrandedLoginView.as_view(), name='incyte',
        kwargs={'branding': 'incyte'}),

    url('^accounts$', views.my_account, name='my_account'),
    url('^logout$', views.logout, name='logout'),

    url(r'^tags$', views.tag_editor, name='tag_editor'),
    url(r'^tags/(?P<tag_type>cell_lines|drugs)$', views.tag_editor,
        name='tag_editor'),
    # url(r'^ajax/tags/set_name$', views.ajax_set_tag_name,
    #     name='ajax_set_tag_name'),
    url(r'^ajax/tags/assign$', views.ajax_assign_tag,
        name='ajax_assign_tag'),

    url(r'platemap$', views.plate_designer,
        kwargs={'dataset_id': None}, name='plate_mapper'),
    url(r'^platemap/(?P<num_wells>\d+)$', views.plate_designer,
        kwargs={'dataset_id': None}, name='plate_mapper'),

    url(r'^dataset/add$', views.dataset_upload, name='plate_upload'),
    url(r'^dataset/(?P<dataset_id>\d+)$', views.view_dataset,
        name='view_dataset'),

    # Redirect dataset page, as it previously had trailing slash
    url(r'^dataset/(?P<dataset_id>\d+)/$', RedirectView.as_view(
        pattern_name='thunorweb:view_dataset', permanent=True)),

    url(r'^dataset/(?P<dataset_id>\d+)/permissions$',
        views.view_dataset_permissions, name='view_dataset_permissions'),
    url(r'^dataset/(?P<dataset_id>\d+)/upload$', views.dataset_upload,
        name='plate_upload'),
    url(r'^dataset/(?P<dataset_id>\d+)/annotate$', views.plate_designer,
        name='plate_designer'),

    url(r'^dataset/(?P<dataset_id>\d+)/download/annotations$',
        views.xlsx_get_annotation_data, name='download_dataset_annotation'),
    url(r'^dataset/(?P<dataset_id>\d+)/download/assays$',
        views.xlsx_get_assay_data, name='download_dataset_assays'),
    url(r'^dataset/(?P<dataset_id>\d+)/download/hdf5$',
        views.download_dataset_hdf5, name='download_dataset_hdf5'),
    url(r'^dataset/(?P<dataset_id>\d+)/download/fit_params$',
        views.download_dip_fit_params, name='download_dip_fit_params'),

    url(r'^plots$', views.plots, name='plots'),

    url(r'^ajax/plot\.(?P<file_type>\w+)$', views.ajax_get_plot,
        name='ajax_plot'),

    url(r'^ajax/dataset/(?P<dataset_id>\d+)(,(?P<dataset2_id>\d+))?/groupings$',
        views.ajax_get_dataset_groupings, name='ajax_dataset_groupings'),
    url(r'^ajax/dataset/set-permission$',
        views.ajax_set_dataset_group_permission,
        name='ajax_set_dataset_group_permission'),
    url(r'^ajax/dataset/delete', views.ajax_delete_dataset,
        name='ajax_delete_dataset'),

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
    url(r'^ajax/dataset/by-group/(?P<group_id>\d+|Public)',
        views.ajax_get_datasets_group, name='ajax_get_datasets_by_group'),

    url(r'^ajax/dataset/create', views.ajax_create_dataset,
        name='ajax_create_dataset'),
    url(r'^ajax/cellline/create', views.ajax_create_cellline,
        name='ajax_create_cellline'),
    url(r'^ajax/drug/create', views.ajax_create_drug,
        name='ajax_create_drug')
]
