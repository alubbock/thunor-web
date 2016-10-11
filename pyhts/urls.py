from django.conf.urls import url, include

from . import views

app_name = 'pyhts'
urlpatterns = [
    url(r'^$', views.home, name='home'),
    url('^logout$', views.logout, name='logout'),
    url(r'^plate$', views.plate_designer, name='plate_designer'),
]
