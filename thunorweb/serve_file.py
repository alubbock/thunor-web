import os
import magic
from django.http import HttpResponse
from django.conf import settings
from django.views.static import serve


def serve_file(request, full_file_name, rename_to=None, content_type=None):
    """
    Serve a static file, either directly or using NGINX X-accel-redirect

    Parameters
    ----------
    request
    full_file_name
    rename_to
    content_type

    Returns
    -------

    """
    if settings.DEBUG or settings.DJANGO_SERVE_FILES_DIRECTLY:
        response = serve(request, os.path.basename(full_file_name),
                         os.path.dirname(full_file_name))
    else:
        response = _nginx_file(full_file_name,
                               rename_to=rename_to,
                               content_type=content_type)

    return response


def _nginx_file(filename, rename_to=None, content_type=None):
    """
    Serve a file using nginx's X-Accel-Redirect header

    Parameters
    ----------
    filename: str
        File name. Must be a full filename contained in Django's MEDIA_ROOT
        (not a subdirectory).
    rename_to: str or None
        Rename to this file name for the download
    content_type: str or None
        A mime type. Auto-detected if set to None.

    Returns
    -------
    An HttpResponse object with an X-Accel-Redirect

    """
    response = HttpResponse(
        content_type=(content_type or magic.from_file(filename, mime=True)))
    basename = os.path.basename(filename)
    response['Content-Disposition'] = 'attachment; filename="{}"'.format(
        rename_to or basename)
    response['X-Accel-Redirect'] = os.path.join(settings.DOWNLOADS_URL,
                                                basename)
    return response
