from django.conf.urls import include, url
from django.conf import settings
from django.contrib import admin

from reports import admin as reports_admin

admin.autodiscover()


urlpatterns = [
    url(r'^reports/', include(reports_admin.site.urls)),
    # default admin interface
    url(r'^admin/', include(admin.site.urls)),
]

if 'debug_toolbar' in settings.INSTALLED_APPS:
    import debug_toolbar
    urlpatterns.append(
        url(r'^__debug__/', include(debug_toolbar.urls))
    )
