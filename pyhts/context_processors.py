from django.conf import settings


def site_branding(request):
    return {'SITE_NAME': settings.SITE_NAME}
