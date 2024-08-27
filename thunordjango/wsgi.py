"""
WSGI config for web project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.10/howto/deployment/wsgi/
"""

import os
import sys
from django.core.wsgi import get_wsgi_application
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "thunordjango.settings")

application = get_wsgi_application()

application({
    'REQUEST_METHOD': 'GET',
    'SERVER_NAME': '127.0.0.1',
    'SERVER_PORT': 8080,
    'PATH_INFO': '/warmup/',
    'HTTP_HOST': settings.HOSTNAME,
    'wsgi.input': sys.stdin,
}, lambda x, y: None)  # call the entry-point function
