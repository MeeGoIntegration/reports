# Django settings for reports project.
import ConfigParser
import json
from os.path import dirname, expanduser, isdir, join

from django.core.exceptions import ImproperlyConfigured

PROJECT_DIR = dirname(__file__)

config = ConfigParser.ConfigParser()
# Read defaults
config.readfp(open(join(PROJECT_DIR, "reports.conf")))
# Read overrides from etc and local file for developement setup
config.read([
    "/etc/reports/reports.conf",
    "local.conf",
])


URL_PREFIX = config.get('web', 'url_prefix')

# Change this to False when developing locally
DEBUG = config.getboolean('base', 'debug')
TEMPLATE_DEBUG = DEBUG

admin_emails = config.get('base', 'admin_emails')
if admin_emails:
    ADMINS = [
        ('Admin', email.strip()) for email in admin_emails.split(',')
    ]
else:
    ADMINS = []

MANAGERS = ADMINS

# Make this unique, and don't share it with anybody.
SECRET_KEY = config.get('base', 'secret_key')

YUM_CACHE_DIR = config.get('base', 'yum_cache_dir')
if not YUM_CACHE_DIR:
    YUM_CACHE_DIR = expanduser("~")
if not isdir(YUM_CACHE_DIR):
    raise ImproperlyConfigured(
        'YUM_CACHE_DIR %s is not directory' % YUM_CACHE_DIR
    )

_db_options = json.loads(config.get('db', 'options'))
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.' + config.get('db', 'engine'),
        'NAME': config.get('db', 'name'),
        'USER': config.get('db', 'user'),
        'PASSWORD': config.get('db', 'pass'),
        'HOST': config.get('db', 'host'),
        'PORT': config.get('db', 'port'),
        'OPTIONS': _db_options,
    }
}

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# In a Windows environment this must be set to your system time zone.
TIME_ZONE = 'UTC'

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = 'en-us'

SITE_ID = 1

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = False

# If you set this to False, Django will not format dates, numbers and
# calendars according to the current locale.
USE_L10N = False

# If you set this to False, Django will not use timezone-aware datetimes.
USE_TZ = True

# Absolute path to the directory static files should be collected to.
# Don't put anything in this directory yourself; store your static files
# in apps' "static/" subdirectories and in STATICFILES_DIRS.
# Example: "/home/media/media.lawrence.com/static/"
STATIC_ROOT = config.get('web', 'static_root')

# URL prefix for static files.
# Example: "http://media.lawrence.com/static/"
STATIC_URL = config.get('web', 'static_url')

# Additional locations of static files
STATICFILES_DIRS = (
    # Put strings here, like "/home/html/static" or "C:/www/django/static".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
    # join(PROJECT_DIR, 'reports/static'),
)

# List of finder classes that know how to find static files in
# various locations.
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    # 'django.contrib.staticfiles.finders.DefaultStorageFinder',
)

# List of callables that know how to import templates from various sources.
TEMPLATE_LOADERS = (
    ('django.template.loaders.cached.Loader', [
        'django.template.loaders.filesystem.Loader',
        'django.template.loaders.app_directories.Loader',
    ]
    ),
)

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
)

ROOT_URLCONF = 'reports.urls'
# Python dotted path to the WSGI application used by Django's runserver.
WSGI_APPLICATION = 'reports.wsgi.application'

TEMPLATE_DIRS = (
    # Put strings here, like "/home/html/django_templates" or
    # "C:/www/django/templates".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
    join(PROJECT_DIR, 'templates'),
)

# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error when DEBUG=False.
# See http://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        }
    },
    'handlers': {
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler'
        }
    },
    'loggers': {
        'django.request': {
            'handlers': ['mail_admins'],
            'level': 'ERROR',
            'propagate': True,
        },
    }
}

if config.getboolean('web', 'use_http_remote_user'):
    MIDDLEWARE_CLASSES += (
        'django.contrib.auth.middleware.RemoteUserMiddleware',
    )
    AUTHENTICATION_BACKENDS = (
        'reports.repo.models.RemoteStaffBackend',
    )

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.admin',
    'rest_framework',
    'reports.repo',
    'south',
)

_cache_options = json.loads(config.get('cache', 'options'))

CACHES = {
    'default': {
        'BACKEND': config.get('cache', 'backend'),
        'LOCATION': config.get('cache', 'location'),
        'TIMEOUT': config.get('cache', 'timeout'),
        'OPTIONS': _cache_options,
    }
}

FILE_UPLOAD_MAX_MEMORY_SIZE = 8

if config.getboolean('base', 'use_debug_toolbar'):
    MIDDLEWARE_CLASSES += ('debug_toolbar.middleware.DebugToolbarMiddleware',)
    INSTALLED_APPS += ('debug_toolbar',)
    INTERNAL_IPS = [
        ip.strip() for ip in config.get('base', 'internal_ips').split(',')
    ]
