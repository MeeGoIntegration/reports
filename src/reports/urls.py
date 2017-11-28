from django.conf.urls import include, patterns, url
from django.conf import settings
from django.contrib import admin
from django.views.generic import TemplateView
from rest_framework import routers

from reports.repo import views as repo_views

admin.autodiscover()

router = routers.DefaultRouter()
router.register(r'repo', repo_views.RepoViewSet)
router.register(r'reposerver', repo_views.RepoServerViewSet)
router.register(r'releases', repo_views.ReleaseViewSet)

urlpatterns = patterns(
    '',
    (
        r'^%s(?P<path>.*)$' % settings.MEDIA_URL,
        'django.views.static.serve', {
            'document_root': settings.MEDIA_ROOT,
            'show_indexes': True,
        }
    ),
    url(r'^api/', include(router.urls)),
    (r'^releases/$', repo_views.releases, {}),
    (r'^/$', TemplateView.as_view(template_name='index.html')),
    url(r'', include(admin.site.urls)),
)

if settings.URL_PREFIX:
    urlpatterns = patterns(
        '',
        (r'%s/' % settings.URL_PREFIX, include(urlpatterns)),
    )
