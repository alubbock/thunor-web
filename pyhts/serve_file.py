import os
import magic
from django.http import HttpResponse
from django.conf import settings


def nginx_file(filename, rename_to=None, content_type=None,
               set_permissions=False):
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
    set_permissions: bool
        A mime type

    Returns
    -------
    An HttpResponse object with an X-Accel-Redirect

    """
    if set_permissions:
        os.chmod(filename, 0o0604)
    response = HttpResponse(
        content_type=(content_type or magic.from_file(filename, mime=True)))
    basename = os.path.basename(filename)
    response['Content-Disposition'] = 'attachment; filename={}'.format(
        rename_to or basename)
    response['X-Accel-Redirect'] = os.path.join(settings.MEDIA_URL, filename)
    return response
