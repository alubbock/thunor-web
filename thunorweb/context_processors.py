from django.conf import settings


def thunor_options(request):
    return {'SITE_NAME': settings.SITE_NAME,
            'SIGNUP_OPEN': not settings.INVITATIONS_INVITATION_ONLY,
            'LOGIN_REQUIRED': settings.LOGIN_REQUIRED}
