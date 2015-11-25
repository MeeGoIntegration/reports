# Django settings for reports project.
from os.path import abspath, dirname, join
PROJECT_DIR = dirname(__file__)

CONFIG="/etc/skynet/reports.conf"

import ConfigParser
config = ConfigParser.ConfigParser()
try:
    config.readfp(open(CONFIG))
except Exception:
    try:
        # during docs build
        config.readfp(open("src/reports/reports.conf"))
    except IOError:
        # when developing it is in cwd
        config.readfp(open("reports.conf"))

URL_PREFIX = config.get('web', 'url_prefix')
static_media_collect = config.get('web', 'static_media_collect')

# Change this to False when developing locally
PRODUCTION = False
DEBUG = True
TEMPLATE_DEBUG = DEBUG

ADMINS = (
    ('Islam Amer', 'islam.amer@jollamobile.com'),
)

MANAGERS = ADMINS

db_engine = config.get('db', 'db_engine')
db_name = config.get('db', 'db_name')
db_user = config.get('db', 'db_user')
db_pass = config.get('db', 'db_pass')
db_host = config.get('db', 'db_host')

DATABASES = {
            'default': {
                'ENGINE' : 'django.db.backends.' + db_engine,
                'NAME' : db_name,
                'USER' : db_user,
                'PASSWORD' : db_pass,
                'HOST' : db_host,
                'PORT' : '',
                }
            }

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# In a Windows environment this must be set to your system time zone.
TIME_ZONE = 'Europe/Helsinki'

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = 'en-us'

SITE_ID = 1

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = True

# If you set this to False, Django will not format dates, numbers and
# calendars according to the current locale.
USE_L10N = True

# If you set this to False, Django will not use timezone-aware datetimes.
USE_TZ = True

# Absolute filesystem path to the directory that will hold user-uploaded files.
# Example: "/home/media/media.lawrence.com/media/"
MEDIA_ROOT = '/srv/www/reports/media/'

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash.
# Examples: "http://media.lawrence.com/media/", "http://example.com/media/"
MEDIA_URL = '/media/'

# Absolute path to the directory static files should be collected to.
# Don't put anything in this directory yourself; store your static files
# in apps' "static/" subdirectories and in STATICFILES_DIRS.
# Example: "/home/media/media.lawrence.com/static/"
STATIC_ROOT = '/srv/www/reports/site_media/'

# URL prefix for static files.
# Example: "http://media.lawrence.com/static/"
STATIC_URL = "/" + URL_PREFIX + '/site_media/'

# Additional locations of static files
STATICFILES_DIRS = (
    # Put strings here, like "/home/html/static" or "C:/www/django/static".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
    #join(PROJECT_DIR, 'reports/static'),
)

# List of finder classes that know how to find static files in
# various locations.
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
#    'django.contrib.staticfiles.finders.DefaultStorageFinder',
)

# Make this unique, and don't share it with anybody.
SECRET_KEY = config.get('web', 'secret_key')


# List of callables that know how to import templates from various sources.
TEMPLATE_LOADERS = (
   ('django.template.loaders.cached.Loader', (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
#     'django.template.loaders.eggs.Loader',
   )),
)

#TEMPLATE_CONTEXT_PROCESSORS = (
#    "django.contrib.auth.context_processors.auth",
#    "django.core.context_processors.debug",
#    "django.core.context_processors.i18n",
#    "django.core.context_processors.media",
#    "django.core.context_processors.static",
#    "django.core.context_processors.tz",
#    "django.contrib.messages.context_processors.messages"
#)

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    #'django.middleware.gzip.GZipMiddleware',
    # Uncomment the next line for simple clickjacking protection:
    # 'django.middleware.clickjacking.XFrameOptionsMiddleware',
)

ROOT_URLCONF = 'reports.urls'
# Python dotted path to the WSGI application used by Django's runserver.
WSGI_APPLICATION = 'reports.wsgi'

TEMPLATE_DIRS = (
    # Put strings here, like "/home/html/django_templates" or "C:/www/django/templates".
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

if PRODUCTION:
    MIDDLEWARE_CLASSES += ('django.contrib.auth.middleware.RemoteUserMiddleware',)
    AUTH_LDAP_AUTHORIZE_ALL_USERS = True
    AUTH_LDAP_CACHE_GROUPS = True
    AUTH_LDAP_GROUP_CACHE_TIMEOUT = 300

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

CACHE_LIFETIME = 60 * 60 * 24

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'reports_cache_table',
        'TIMEOUT': CACHE_LIFETIME,
        'OPTIONS': {
            'MAX_ENTRIES' : 10000,
        }
    }
}

FILE_UPLOAD_MAX_MEMORY_SIZE = 8
#MIDDLEWARE_CLASSES = MIDDLEWARE_CLASSES + ('snippetscream.ProfileMiddleware',)
#MIDDLEWARE_CLASSES = MIDDLEWARE_CLASSES + ('debug_toolbar.middleware.DebugToolbarMiddleware',)
#INSTALLED_APPS = INSTALLED_APPS + ('debug_toolbar',)
#INTERNAL_IPS = ('127.0.0.1','197.133.218.195')
