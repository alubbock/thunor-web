"""
WSGI config for web project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.10/howto/deployment/wsgi/
"""

import os
from django.core.wsgi import get_wsgi_application
try:
    from uwsgidecorators import postfork
    from django.test.client import Client
except:
    postfork = lambda func: func

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "thunordjango.settings")

application = get_wsgi_application()

@postfork
def initialise():
    Client().get('/')
