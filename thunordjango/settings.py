"""
Django settings for web project.

Generated by 'django-admin startproject' using Django 1.10.1.

For more information on this file, see
https://docs.djangoproject.com/en/1.10/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.10/ref/settings/
"""

import os
import sentry_sdk
import sys
import thunorweb
from django.contrib import messages
import errno
import logging

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables for .env file, if present
env_file = os.path.join(BASE_DIR, 'thunor-dev.env')
try:
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('#') or not line:
                continue
            var_name, var_val = line.split('=', 1)
            if (var_val[0] == "'" and var_val[-1] == "'") or \
                    (var_val[0] == '"' and var_val[-1] == '"'):
                var_val = var_val[1:-1]
            print('Setting {} from thunor-dev.env'.format(var_name))
            os.environ[var_name] = var_val
except FileNotFoundError:
    pass

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ['DJANGO_DEBUG'].lower() == 'true'

# Initialise sentry error handler
sentry_sdk.init(
    dsn=os.environ.get('DJANGO_SENTRY_DSN', None),
    environment=os.environ.get('DJANGO_SENTRY_ENVIRONMENT',
                               'development' if DEBUG else 'production'),
    release=thunorweb.__version__,
    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for tracing.
    traces_sample_rate=1.0,
    # Set profiles_sample_rate to 1.0 to profile 100%
    # of sampled transactions.
    # We recommend adjusting this value in production.
    profiles_sample_rate=1.0,
)


logger = logging.getLogger(__name__)

# This is where state-specific files are stored, like uploads/downloads and
# the SQLite database, if applicable
STATE_DIR = os.path.join(BASE_DIR, '_state')

if DEBUG:
    # Add the thunor submodule to the path
    sys.path.insert(0, os.path.join(BASE_DIR, 'thunor'))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ['DJANGO_SECRET_KEY']

HOSTNAME = os.environ.get('DJANGO_HOSTNAME', 'localhost')
ALLOWED_HOSTS = [HOSTNAME, ]

INTERNAL_IPS = '127.0.0.1'

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.sites',
    'django.contrib.staticfiles',
    'thunorweb.apps.ThunorConfig',
    'custom_user',
    'allauth',
    'allauth.account',
    'invitations',
    'guardian',
    'crispy_forms',
    'crispy_bootstrap3',
    'webpack_loader'
]


CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap3"

CRISPY_TEMPLATE_PACK = "bootstrap3"

SITE_ID = 1
MIGRATION_MODULES = {
    'sites': 'thunorweb.fixtures.sites_migrations',
}

MIDDLEWARE = []

if DEBUG:
    try:
        import debug_toolbar
        INSTALLED_APPS += ['debug_toolbar']
        MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
    except ImportError:
        pass

    MIDDLEWARE += ['thunorweb.debug.NonHtmlDebugToolbarMiddleware']
    # INSTALLED_APPS += ['debug_panel', 'django_extensions']
    # MIDDLEWARE += ['debug_panel.middleware.DebugPanelMiddleware']

MIDDLEWARE += [
    'allauth.account.middleware.AccountMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.http.ConditionalGetMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'thunordjango.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, '_state/template-overrides')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'thunorweb.context_processors.thunor_options'
            ],
        },
    },
]

WSGI_APPLICATION = 'thunordjango.wsgi.application'

EMAIL_USE_TLS = True
EMAIL_ENABLED = True
try:
    EMAIL_HOST = os.environ['DJANGO_EMAIL_HOST']
    EMAIL_PORT = os.environ['DJANGO_EMAIL_PORT']
    EMAIL_HOST_USER = os.environ['DJANGO_EMAIL_USER']
    EMAIL_HOST_PASSWORD = os.environ['DJANGO_EMAIL_PASSWORD']
    DEFAULT_FROM_EMAIL = os.environ.get('DJANGO_EMAIL_FROM', EMAIL_HOST_USER)
except KeyError:
    if DEBUG:
        logger.warning('Email configuration missing; email sending disabled')
        EMAIL_ENABLED = False
    else:
        raise

# Database
# https://docs.djangoproject.com/en/1.10/ref/settings/#databases

DATABASE_SETTING = os.environ.get('DJANGO_DATABASE', 'postgres')

DB_MAX_BATCH_SIZE = None

if DATABASE_SETTING == 'postgres':
    # Bigger batch size is faster but uses more memory
    DB_MAX_BATCH_SIZE = 100000
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql_psycopg2',
            'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
            'NAME': os.environ.get('POSTGRES_DB', False) or
                    os.environ.get('POSTGRES_USER', 'postgres'),
            'USER': os.environ.get('POSTGRES_USER', 'postgres'),
            'PASSWORD': os.environ['POSTGRES_PASSWORD'],
            'PORT': os.environ.get('POSTGRES_PORT', '')
        }
    }
else:
    raise ValueError('Only DJANGO_DATABASE=postgres is currently supported')

CACHES = {}
if 'DJANGO_REDIS_URL' in os.environ:
    CACHES['default'] = {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': os.environ['DJANGO_REDIS_URL'],
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
elif os.environ.get('DJANGO_DB_CACHE', 'false').lower() == 'true':
    CACHES['default'] = {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'thunor_cache'
    }
elif DEBUG:
    CACHES['default'] = {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'
    }
else:
    CACHES['default'] = {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache'
    }

if 'AWS_S3_SECRET_ACCESS_KEY' in os.environ:
    logger.debug('Enabling S3 storage')
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "bucket_name": os.environ["AWS_S3_BUCKET_NAME"],
                "region_name": os.environ.get("AWS_S3_REGION_NAME"),
                "endpoint_url": os.environ.get("AWS_S3_ENDPOINT_URL")
            }
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    }


AUTH_USER_MODEL = 'custom_user.EmailUser'
AUTHENTICATION_BACKENDS = (
    # Needed to login by username in Django admin, regardless of `allauth`
    'django.contrib.auth.backends.ModelBackend',
    # `allauth` specific authentication methods, such as login by e-mail
    'allauth.account.auth_backends.AuthenticationBackend',
    # Needed for per-object permissions
    'guardian.backends.ObjectPermissionBackend'
)
THUNOR_USE_TLS = os.environ.get(
    'DJANGO_ACCOUNTS_TLS', 'false').lower() == 'true'
ACCOUNT_DEFAULT_HTTP_PROTOCOL = 'https' if THUNOR_USE_TLS else 'http'
ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = os.environ.get(
    'THUNOR_EMAIL_VERIFICATION',
    'none' if DEBUG and not EMAIL_ENABLED else 'mandatory'
)
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_LOGIN_ON_PASSWORD_RESET = True
ACCOUNT_FORMS = {'login': 'thunorweb.forms.CentredAuthForm',
                 'change_password': 'thunorweb.forms.ChangePasswordForm',
                 'reset_password': 'thunorweb.forms.ResetPasswordForm',
                 'reset_password_from_key': 'thunorweb.forms.ResetPasswordKeyForm',
                 'set_password': 'thunorweb.forms.SetPasswordForm',
                 'signup': 'thunorweb.forms.SignUpForm',
                 'add_email': 'thunorweb.forms.AddEmailForm'}
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_EMAIL_SUBJECT_PREFIX = ''

if not DEBUG and THUNOR_USE_TLS:
    SESSION_COOKIE_SECURE = True
    CRSF_COOKIE_SECURE = True

LOGIN_REDIRECT_URL = 'thunorweb:home'

# Can public datasets be accessed without login
LOGIN_REQUIRED = os.environ.get('THUNOR_LOGIN_REQUIRED', 'true').lower() == \
                 'true'

MESSAGE_TAGS = {
    messages.ERROR: 'danger'
}

# Password validation
# https://docs.djangoproject.com/en/1.10/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


INVITATIONS_GONE_ON_ACCEPT_ERROR = False
INVITATIONS_INVITATION_ONLY = os.environ.get('THUNOR_SIGNUP_OPEN',
                                             'false').lower() == 'false'
INVITATIONS_ACCEPT_INVITE_AFTER_SIGNUP = True
ACCOUNT_ADAPTER = 'invitations.models.InvitationsAdapter'
INVITATIONS_ADAPTER = ACCOUNT_ADAPTER

# Internationalization
# https://docs.djangoproject.com/en/1.10/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = False

USE_L10N = False

USE_TZ = True

SHORT_DATETIME_FORMAT = 'Y-m-d H:i:s T'
DATETIME_FORMAT = SHORT_DATETIME_FORMAT

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.10/howto/static-files/

STATIC_URL = os.environ.get('DJANGO_STATIC_URL', '/static/')
CONTAINER_STATIC_ROOT = os.path.join(BASE_DIR, 'static')
if os.path.exists(CONTAINER_STATIC_ROOT):
    STATIC_ROOT = CONTAINER_STATIC_ROOT
else:
    STATIC_ROOT = os.path.join(STATE_DIR, 'thunor-static')
STATICFILES_DIRS = (os.path.join(STATE_DIR, 'webpack-bundles'), )
WEBPACK_LOADER = {
    'DEFAULT': {
        'CACHE': not DEBUG,
        'BUNDLE_DIR_NAME': '',
        'STATS_FILE': os.path.join(STATIC_ROOT, 'webpack-stats.json'),
        'POLL_INTERVAL': 0.1,
        'TIMEOUT': None,
        'IGNORE': [r'.+\.map']
    }
}

MEDIA_ROOT = os.environ.get('DJANGO_MEDIA_ROOT', os.path.join(STATE_DIR,
                                                              'thunor-files'))
MEDIA_URL = os.environ.get('DJANGO_MEDIA_URL', '/_state/thunor-files/')
DATA_UPLOAD_MAX_NUMBER_FIELDS = int(os.environ.get(
    'DJANGO_UPLOAD_MAX_NUMBER_FIELDS', 1000))

# These DOWNLOADS_* settings need to match nginx config unless using S3
DOWNLOADS_PREFIX = 'downloads'
DOWNLOADS_URL = '/_thunor_downloads/'
# Serve static files directly rather than through nginx
DJANGO_SERVE_FILES_DIRECTLY = os.environ.get('DJANGO_SERVE_FILES_DIRECTLY', 'false').lower() == 'true'
# Time to retain datasets after they've been marked for deletion
DATASET_RETENTION_DAYS = 30
# Time to retain uploaded datasets if they're not attached to a dataset
# (i.e. for debugging purposes)
NON_DATASET_UPLOAD_RETENTION_DAYS = 7

LOGGING = {
    'version': 1,
    'disable_existing_loggers': not DEBUG,
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        }
    },
    'formatters': {
        'verbose': {
            'format': '%(levelname)s %(asctime)s %(module)s '
                      '%(process)d %(thread)d %(message)s'
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose'
        }
    },
    'loggers': {
        'root': {
            'level': 'DEBUG' if DEBUG else 'INFO',
            'handlers': [],
        },
        'django.db.backends': {
            'level': 'ERROR',
            'handlers': ['console'],
            'propagate': False,
        },
    },
}

# Quality control settings
THUNOR_REQUIRE_CONTROLS = True
