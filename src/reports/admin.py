from django.conf import settings
from django.contrib.admin.sites import AdminSite
from rest_framework import routers

from reports.repo import views as repo_views

router = routers.DefaultRouter()
router.register(r'repo', repo_views.RepoViewSet)
router.register(r'reposerver', repo_views.RepoServerViewSet)
router.register(r'releases', repo_views.ReleaseViewSet)


class ReportsAdmin(AdminSite):
    index_template = 'index.html'

    def get_urls(self):
        # This method is overriden to get rid of the /<app_label>/ component
        # in the urls.

        from django.conf.urls import url, include
        # Empty registry while we get the default admin urls as we don't want
        # the model admin urls from there
        registry = self._registry
        self._registry = {}
        urlpatterns = super(ReportsAdmin, self).get_urls()
        self._registry = registry

        urlpatterns.extend([
            url(r'^api/', include(router.urls)),
            url(r'^releases/$', repo_views.releases),
        ])

        # Add in each model's views, but without the app label
        valid_app_labels = set()
        for model, model_admin in self._registry.iteritems():
            urlpatterns.append(
                url(r'^%s/' % model._meta.model_name,
                    include(model_admin.urls))
            )
            valid_app_labels.add(model._meta.app_label)

        # Point the app_list url to index as several default templates need it
        if valid_app_labels:
            urlpatterns.append(
                url(r'^(?P<app_label>' + '|'.join(valid_app_labels) + ')/$',
                    self.admin_view(self.index), name='app_list'
                    )
            )

        return urlpatterns

    def index(self, request, extra_context=None):
        if extra_context is None:
            extra_context = {}
        extra_context['shortcuts_template'] = settings.SHORTCUTS_TEMPLATE
        return super(ReportsAdmin, self).index(
            request, extra_context=extra_context
        )


site = ReportsAdmin(name='reports')
