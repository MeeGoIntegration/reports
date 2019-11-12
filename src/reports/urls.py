from django.conf.urls import include, patterns, url
from django.contrib import admin

from reports import admin as reports_admin

admin.autodiscover()


urlpatterns = patterns(
    '',
    url(r'^reports/', include(reports_admin.site.urls)),
    # default admin interface
    url(r'^admin/', include(admin.site.urls)),
)
