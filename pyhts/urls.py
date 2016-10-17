from django.conf.urls import url, include

from . import views

app_name = 'pyhts'
urlpatterns = [
    url(r'^$', views.home, name='home'),
    url('^logout$', views.logout, name='logout'),
    url(r'^upload$', views.PlateUpload.as_view(), name='plate_upload'),
    url(r'^annotate$', views.plate_designer, name='plate_designer'),

    url(r'^ajax/plate/(?P<file_id>\d+)$', views.ajax_get_plates,
        name='ajax_plate_names')
]
